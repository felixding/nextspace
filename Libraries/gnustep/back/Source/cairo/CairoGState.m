
/*
   CairoGState.m

   Copyright (C) 2003 Free Software Foundation, Inc.

   August 31, 2003
   Written by Banlu Kemiyatorn <object at gmail dot com>
   Rewrite: Fred Kiefer <fredkiefer@gmx.de>
   Date: Jan 2006
 
   This file is part of GNUstep.

   This library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Lesser General Public
   License as published by the Free Software Foundation; either
   version 2 of the License, or (at your option) any later version.

   This library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
   Lesser General Public License for more details.

   You should have received a copy of the GNU Lesser General Public
   License along with this library; see the file COPYING.LIB.
   If not, see <http://www.gnu.org/licenses/> or write to the 
   Free Software Foundation, 51 Franklin Street, Fifth Floor, 
   Boston, MA 02110-1301, USA.
*/

#include "config.h"
#include <AppKit/NSAffineTransform.h>
#include <AppKit/NSBezierPath.h>
#include <AppKit/NSColor.h>
#include <AppKit/NSGradient.h>
#include <AppKit/NSGraphics.h>
#include <AppKit/NSImage.h>
#include "cairo/CairoGState.h"
#include "cairo/CairoFontInfo.h"
#include "cairo/CairoSurface.h"
#include "cairo/CairoContext.h"
#include <math.h>


// Macro stolen from base/Header/Additions/GNUstepBase/GSObjRuntime.h
#ifndef	GS_MAX_OBJECTS_FROM_STACK
/**
 * The number of objects to try to get from varargs into an array on
 * the stack ... if there are more than this, use the heap.
 * NB. This MUST be a multiple of 2
 */
#define	GS_MAX_OBJECTS_FROM_STACK	128
#endif

// Macros stolen from base/Source/GSPrivate.h
/**
 * Macro to manage memory for chunks of code that need to work with
 * arrays of items.  Use this to start the block of code using
 * the array and GS_ENDITEMBUF() to end it.  The idea is to ensure that small
 * arrays are allocated on the stack (for speed), but large arrays are
 * allocated from the heap (to avoid stack overflow).
 */
#define	GS_BEGINITEMBUF(P, S, T) { \
  T _ibuf[(S) <= GS_MAX_OBJECTS_FROM_STACK ? (S) : 0]; \
  T *_base = ((S) <= GS_MAX_OBJECTS_FROM_STACK) ? _ibuf \
    : (T*)NSZoneMalloc(NSDefaultMallocZone(), (S) * sizeof(T)); \
  T *(P) = _base;

/**
 * Macro to manage memory for chunks of code that need to work with
 * arrays of items.  Use GS_BEGINITEMBUF() to start the block of code using
 * the array and this macro to end it.
 */
#define	GS_ENDITEMBUF() \
  if (_base != _ibuf) \
    NSZoneFree(NSDefaultMallocZone(), _base); \
  }

static inline double doubleFromUserSpace(NSAffineTransform *ctm, CGFloat d)
{
  if (ctm)
    {
      NSSize s = {d, d};

      s = [ctm transformSize: s];
      d = (((s.width > 0.0) ? s.width : -s.width) + 
           ((s.height > 0.0) ? s.height : -s.height)) / 2;
    }
  return d;
}

static inline CGFloat floatToUserSpace(NSAffineTransform *ctm, double d)
{
  if (ctm)
    {
      NSAffineTransform *ictm;
      
      ictm = [ctm copy];
      [ictm invert];
      d = doubleFromUserSpace(ictm, d);
      RELEASE(ictm);
    }
  return (CGFloat)d;
}

static inline cairo_filter_t cairoFilterFromNSImageInterpolation(NSImageInterpolation interpolation)
{
  switch (interpolation)
    {
    case NSImageInterpolationNone: return CAIRO_FILTER_NEAREST;
    case NSImageInterpolationLow: return CAIRO_FILTER_FAST;
    case NSImageInterpolationHigh: return CAIRO_FILTER_BEST;
    default: return CAIRO_FILTER_GOOD;
    }
}


@implementation CairoGState 

+ (void) initialize
{
  if (self == [CairoGState class])
    {
    }
}

- (void) dealloc
{
  if (_ct)
    {
      cairo_destroy(_ct);
    }
  RELEASE(_surface);

  [super dealloc];
}

- (NSString*) description
{
  NSMutableString *description = [[[super description] mutableCopy] autorelease];
  [description appendFormat: @" surface: %@",_surface];
  [description appendFormat: @" context: %p",_ct];
  return [[description copy] autorelease];
}

- (id) copyWithZone: (NSZone *)zone
{
  CairoGState *copy = (CairoGState *)[super copyWithZone: zone];

  RETAIN(_surface);

  if (_ct)
    {
      cairo_status_t status;
 
      // FIXME: Need some way to do a copy
      // but there isnt anything like copy->_ct = cairo_copy(_ct);
#if BUILD_SERVER == SERVER_wayland
      copy->_ct = cairo_create(cairo_get_group_target(_ct));
#else
      copy->_ct = cairo_create(cairo_get_target(_ct));
#endif
      status = cairo_status(copy->_ct);
      if (status != CAIRO_STATUS_SUCCESS)
        {
          NSLog(@"Cairo status '%s' in copy", cairo_status_to_string(status));
          copy->_ct = NULL;
        }
      else
        {
          cairo_path_t *cpath;
          cairo_matrix_t local_matrix;
#if CAIRO_VERSION > CAIRO_VERSION_ENCODE(1, 4, 0)
          cairo_rectangle_list_t *clip_rects;
          int	num_dashes;
#endif

          cairo_get_matrix(_ct, &local_matrix);
          cairo_set_matrix(copy->_ct, &local_matrix);
          status = cairo_status(copy->_ct);
          if (status != CAIRO_STATUS_SUCCESS)
            {
              NSLog(@"Cairo status '%s' in set matrix", cairo_status_to_string(status));
            }

          cairo_set_operator(copy->_ct, cairo_get_operator(_ct));
          cairo_set_source(copy->_ct, cairo_get_source(_ct));
          cairo_set_tolerance(copy->_ct, cairo_get_tolerance(_ct));
          cairo_set_antialias(copy->_ct, cairo_get_antialias(_ct));
          cairo_set_line_width(copy->_ct, cairo_get_line_width(_ct));
          cairo_set_line_cap(copy->_ct, cairo_get_line_cap(_ct));
          cairo_set_line_join(copy->_ct, cairo_get_line_join(_ct));
          cairo_set_miter_limit(copy->_ct, cairo_get_miter_limit(_ct));

#if CAIRO_VERSION > CAIRO_VERSION_ENCODE(1, 4, 0)
          // In cairo 1.4 there is a way get the dash.
          num_dashes = cairo_get_dash_count(_ct);
          if (num_dashes != 0)
            {
              double dash_offset;
              GS_BEGINITEMBUF(dashes, num_dashes, double);

              cairo_get_dash(_ct, dashes, &dash_offset);
              cairo_set_dash (copy->_ct, dashes, num_dashes, dash_offset);
              GS_ENDITEMBUF();
            }

          // In cairo 1.4 there also is a way to get the current clipping path
          cairo_new_path(copy->_ct);
          clip_rects = cairo_copy_clip_rectangle_list(_ct);
          status = clip_rects->status;
          if (status == CAIRO_STATUS_SUCCESS)
            {
              int i;

              if (cairo_version() >= CAIRO_VERSION_ENCODE(1, 6, 0))
                {
                  for (i = 0; i < clip_rects->num_rectangles; i++)
                    {
                      cairo_rectangle_t rect = clip_rects->rectangles[i];

                      cairo_rectangle(copy->_ct, rect.x, rect.y, 
                                      rect.width, rect.height);
                    }
                }
              else
                {
                  for (i = 0; i < clip_rects->num_rectangles; i++)
                    {
                      cairo_rectangle_t rect = clip_rects->rectangles[i];
                      NSSize size = [_surface size];

                      cairo_rectangle(copy->_ct, rect.x, 
                                      /* This strange computation is due 
                                         to the device offset missing for 
                                         clip rects in cairo < 1.6.0.  */
                                      rect.y + 2*(offset.y - size.height), 
                                      rect.width, rect.height);
                    }
                }
              /* Rectangles describe a union, including an empty clip. */
              cairo_clip(copy->_ct);
            }
          else if (status == CAIRO_STATUS_CLIP_NOT_REPRESENTABLE)
            {
              // We cannot get the exact clip, so we do the best we can
              double x1;
              double y1;
              double x2;
              double y2;

              cairo_clip_extents(_ct, &x1, &y1, &x2, &y2);
              cairo_rectangle(copy->_ct, x1, y1, x2 - x1, y2 - y1);
              cairo_clip(copy->_ct);
            }
          else
            {
              NSLog(@"Cairo status '%s' in copy clip", cairo_status_to_string(status));
            }

          cairo_rectangle_list_destroy(clip_rects);
#endif
          cpath = cairo_copy_path(_ct);
          status = cpath->status;
          if (status != CAIRO_STATUS_SUCCESS)
            {
              /*
                Due to an interesting programming concept in cairo this does not
                mean that an error has occured. It may as well just be that the
                old path had no elements.
                At least in cairo 1.4.10 (See file cairo-path.c, line 379).
              */
              // NSLog(@"Cairo status '%s' in copy path", cairo_status_to_string(status));
            }
          else
            {
              cairo_append_path(copy->_ct, cpath);
            }
          cairo_path_destroy(cpath);

        }
    }

  return copy;
}

- (void) GSCurrentSurface: (CairoSurface **)surface : (int *)x : (int *)y
{
  if (x)
    *x = offset.x;
  if (y)
    *y = offset.y;
  if (surface)
    {
      *surface = _surface;
    }
}

- (void) GSSetSurface: (CairoSurface *)surface : (int)x : (int)y
{
  ASSIGN(_surface, surface);
  [self setOffset: NSMakePoint(x, y)];
  [self DPSinitgraphics];
}

- (void) setOffset: (NSPoint)theOffset
{
  if (_surface != nil)
    {
      NSSize size = [_surface size];

      double sx, sy;
      cairo_surface_get_device_scale([_surface surface], &sx, &sy);
      cairo_surface_set_device_offset([_surface surface], -theOffset.x * sx,
                                      (theOffset.y - size.height) * sy);
    }
  [super setOffset: theOffset];
}

- (void) showPage
{
  if (_ct)
    {
      cairo_show_page(_ct);
    }
}

/*
 * Color operations
 */
- (void)GSSetPatterColor:(NSImage *)image
{
  NSSize size = [image size];
  NSImageRep *rep = [image bestRepresentationForDevice:nil];
  if (!image || !rep || !isfinite(size.width) || !isfinite(size.height) ||
      size.width <= 0 || size.height <= 0)
    [NSException raise:NSInvalidArgumentException format:@"A pattern needs a valid image and positive logical size."];
  [super GSSetPatterColor:image];
  if (!_ct) return;

  double dx, dy;
  cairo_surface_get_device_scale(cairo_get_target(_ct), &dx, &dy);
  NSAffineTransformStruct view = [ctm transformStruct];
  NSInteger width = [rep pixelsWide], height = [rep pixelsHigh];
  if (width <= 0) width = ceil(size.width * hypot(view.m11 * dx, view.m12 * dy));
  if (height <= 0) height = ceil(size.height * hypot(view.m21 * dx, view.m22 * dy));
  cairo_surface_t *tile = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, width, height);
  if (cairo_surface_status(tile) != CAIRO_STATUS_SUCCESS) {
    cairo_surface_destroy(tile);
    [NSException raise:NSMallocException format:@"Could not allocate pattern image surface."];
  }
  @try {
    /* Reuse ordinary image drawing for pixel formats, premultiplication and
       channel order. Cairo owns the resulting pixels for the pattern lifetime. */
    [drawcontext DPSgsave];
    @try {
      CairoGState *state = (CairoGState *)[(GSContext *)drawcontext currentGState];
      cairo_destroy(state->_ct);
      state->_ct = cairo_create(tile);
      cairo_scale(state->_ct, width / size.width, -height / size.height);
      cairo_translate(state->_ct, 0, -size.height);
      [drawcontext GSSetCTM:[NSAffineTransform transform]];
      [rep drawInRect:NSMakeRect(0, 0, size.width, size.height)];
    } @finally {
      [drawcontext DPSgrestore];
    }
    NSAffineTransform *inverse = [[ctm copy] autorelease];
    [inverse invert];
    NSAffineTransformStruct t = [inverse transformStruct];
    NSPoint phase = [self patternPhase];
    double sx = width / size.width, sy = height / size.height;
    cairo_matrix_t matrix;
    cairo_matrix_init(&matrix, sx * t.m11, -sy * t.m12, sx * t.m21, -sy * t.m22,
      sx * (t.tX - phase.x), height - sy * (t.tY - phase.y));
    cairo_pattern_t *source = cairo_pattern_create_for_surface(tile);
    cairo_pattern_set_matrix(source, &matrix);
    cairo_pattern_set_extend(source, CAIRO_EXTEND_REPEAT);
    cairo_pattern_set_filter(source, cairoFilterFromNSImageInterpolation([drawcontext imageInterpolation]));
    cairo_set_source(_ct, source);
    cairo_pattern_destroy(source);
  } @finally {
    cairo_surface_destroy(tile);
  }
}

- (void)setPatternPhase:(NSPoint)phase
{
  NSPoint previous = [self patternPhase];
  [super setPatternPhase:phase];
  if (!_ct || !pattern) return;
  cairo_pattern_t *source = cairo_get_source(_ct);
  cairo_surface_t *tile;
  if (cairo_pattern_get_surface(source, &tile) != CAIRO_STATUS_SUCCESS ||
      cairo_surface_get_type(tile) != CAIRO_SURFACE_TYPE_IMAGE) return;
  NSSize size = [pattern size];
  cairo_matrix_t matrix;
  cairo_pattern_get_matrix(source, &matrix);
  matrix.x0 -= (phase.x - previous.x) * cairo_image_surface_get_width(tile) / size.width;
  matrix.y0 += (phase.y - previous.y) * cairo_image_surface_get_height(tile) / size.height;
  /* Sources are shared by saved graphics states. Give this state its own
     phase matrix while retaining the same immutable tile pixels. */
  cairo_pattern_t *shifted = cairo_pattern_create_for_surface(tile);
  cairo_pattern_set_matrix(shifted, &matrix);
  cairo_pattern_set_extend(shifted, cairo_pattern_get_extend(source));
  cairo_pattern_set_filter(shifted, cairo_pattern_get_filter(source));
  cairo_set_source(_ct, shifted);
  cairo_pattern_destroy(shifted);
}

/*
 * Text operations
 */

- (void) _setPoint
{
  NSPoint p;

  p = [path currentPoint];
  cairo_move_to(_ct, p.x, p.y);
}

- (void) DPScharpath: (const char *)s : (int)b
{
  if (_ct)
    {
      GS_BEGINITEMBUF(c, b + 1, char);

      [self _setPoint];
      memcpy(c, s, b);
      c[b] = 0;
      cairo_text_path(_ct, c);
      GS_ENDITEMBUF();
      if (cairo_status(_ct) == CAIRO_STATUS_SUCCESS)
        {
          cairo_path_t *cpath;
          cairo_path_data_t *data;
          int i;
         
          cpath = cairo_copy_path(_ct);
          
          for (i = 0; i < cpath->num_data; i += cpath->data[i].header.length) 
            {
              data = &cpath->data[i];
              switch (data->header.type) 
                {
                  case CAIRO_PATH_MOVE_TO:
                    [path moveToPoint: NSMakePoint(data[1].point.x, data[1].point.y)];
                    break;
                  case CAIRO_PATH_LINE_TO:
                    [path lineToPoint: NSMakePoint(data[1].point.x, data[1].point.y)];
                    break;
                  case CAIRO_PATH_CURVE_TO:
                    [path curveToPoint: NSMakePoint(data[3].point.x, data[3].point.y) 
                          controlPoint1: NSMakePoint(data[1].point.x, data[1].point.y)
                          controlPoint2: NSMakePoint(data[2].point.x, data[2].point.y)];
                    break;
                  case CAIRO_PATH_CLOSE_PATH:
                    [path closePath];
                    break;
                }
            }
          cairo_path_destroy(cpath);
        }
    }
}

- (void) DPSshow: (const char *)s
{
  if (_ct)
    {
      cairo_matrix_t local_matrix;
      NSAffineTransformStruct matrix = [ctm transformStruct];
      device_color_t c;

      c = strokeColor;
      gsColorToRGB(&c);
      // The underlying concept does not allow to determine if alpha is set or not.
      cairo_set_source_rgba(_ct, c.field[0], c.field[1], c.field[2], c.field[AINDEX]);

      [self _setPoint];
      cairo_save(_ct);
      cairo_matrix_init(&local_matrix, matrix.m11, 0, 0,
                        matrix.m22, 0, 0);
      cairo_transform(_ct, &local_matrix);
      // Undo the flip
      cairo_matrix_init_scale(&local_matrix, 1, -1);
      cairo_matrix_translate(&local_matrix, 0,  -[_surface size].height);
      cairo_transform(_ct, &local_matrix);

      cairo_show_text(_ct, s);

      cairo_restore(_ct);
    }
}

- (void) GSSetFont: (GSFontInfo *)fontref
{
  [super GSSetFont: fontref];

  if (_ct)
    {
      cairo_set_scaled_font(_ct, ((CairoFontInfo *)font)->_scaled);
    }
}

- (void) GSSetFontSize: (CGFloat)size
{
  if (_ct)
    {
      cairo_set_font_size(_ct, doubleFromUserSpace(ctm, size));
    }
}

- (void) GSShowText: (const char *)string : (size_t)length
{
  if (_ct)
    {
      device_color_t c;
      GS_BEGINITEMBUF(chars, length + 1, char);

      c = strokeColor;
      gsColorToRGB(&c);
      // The underlying concept does not allow to determine if alpha is set or not.
      cairo_set_source_rgba(_ct, c.field[0], c.field[1], c.field[2], c.field[AINDEX]);

      [self _setPoint];
      memcpy(chars, string, length);
      chars[length] = 0;
      cairo_show_text(_ct, chars);
      GS_ENDITEMBUF();
    }
}

- (void) GSShowGlyphsWithAdvances: (const NSGlyph *)glyphs : (const NSSize *)advances : (size_t) length
{
  // The legacy path retains its existing glyph layout.
  if (_ct)
    {
      cairo_matrix_t local_matrix;
      NSAffineTransformStruct	matrix = [ctm transformStruct];
      device_color_t c;

      c = strokeColor;
      gsColorToRGB(&c);
      // The underlying concept does not allow to determine if alpha is set or not.
      cairo_set_source_rgba(_ct, c.field[0], c.field[1], c.field[2], c.field[AINDEX]);

      [self _setPoint];
      // FIXME: Hack to get font in rotated view working
      cairo_save(_ct);
      cairo_matrix_init(&local_matrix, matrix.m11, matrix.m12, matrix.m21,
                        matrix.m22, 0, 0);
      cairo_transform(_ct, &local_matrix);
      // Undo the 
      cairo_matrix_init_scale(&local_matrix, 1, -1);
      cairo_matrix_translate(&local_matrix, 0,  -[_surface size].height);
      cairo_transform(_ct, &local_matrix);

#if BUILD_SERVER == SERVER_wayland
      if ([_surface isDrawingToScreen])
        [(CairoFontInfo *)font drawGlyphs:glyphs advances:advances length:length on:_ct];
      else
#endif
        [(CairoFontInfo *)font drawGlyphs: glyphs
				 length: length
				     on: _ct];

      double x, y;
      cairo_get_current_point(_ct, &x, &y);
      cairo_user_to_device(_ct, &x, &y);
      
      cairo_restore(_ct);
      
      // reset the current point
      cairo_device_to_user(_ct, &x, &y);
      [path moveToPoint: NSMakePoint(x,y)];
    }
}

/*
 * GState operations
 */

- (void) DPSinitgraphics
{
  cairo_status_t status;
  cairo_matrix_t local_matrix;

  [super DPSinitgraphics];

  if (_ct)
    {
      cairo_destroy(_ct);
      _ct = NULL;
    }
  if (!_surface)
    {
      return;
    }
  _ct = cairo_create([_surface surface]);
  status = cairo_status(_ct);
  if (status != CAIRO_STATUS_SUCCESS)
    {
      NSLog(@"Cairo status '%s' in DPSinitgraphics", cairo_status_to_string(status));
      _ct = NULL;
      return;
    }
  
  // cairo draws the other way around.
  // At this point in time viewIsFlipped has not been set, but it is
  // OK to ignore this here, as in that case the matrix will later 
  // get flipped by GUI,
  cairo_matrix_init_scale(&local_matrix, 1, -1);
  cairo_matrix_translate(&local_matrix, 0,  -[_surface size].height);
  cairo_set_matrix(_ct, &local_matrix);

  // Cairo's default line width is 2.0
  cairo_set_line_width(_ct, 1.0);
  cairo_set_operator(_ct, CAIRO_OPERATOR_OVER);
  cairo_new_path(_ct);
}

- (void) DPScurrentflat: (CGFloat *)flatness
{
  if (_ct)
    {
      *flatness = (CGFloat)cairo_get_tolerance(_ct) * 2;
    }
}

- (void) DPScurrentlinecap: (int *)linecap
{
  cairo_line_cap_t lc;

  if (_ct)
    {
      lc = cairo_get_line_cap(_ct);
      *linecap = lc;
    }
  /*
     switch (lc)
     {
     case CAIRO_LINE_CAP_BUTT:
     *linecap = 0;
     break;
     case CAIRO_LINE_CAP_ROUND:
     *linecap = 1;
     break;
     case CAIRO_LINE_CAP_SQUARE:
     *linecap = 2;
     break;
     default:
     NSLog(@"ERROR Line cap unknown");
     exit(-1);
     }
   */
}

- (void) DPScurrentlinejoin: (int *)linejoin
{
  cairo_line_join_t lj;

  if (_ct)
    {
      lj = cairo_get_line_join(_ct);
      *linejoin = lj;
    }
  /*
     switch (lj)
     {
     case CAIRO_LINE_JOIN_MITER:
     *linejoin = 0;
     break;
     case CAIRO_LINE_JOIN_ROUND:
     *linejoin = 1;
     break;
     case CAIRO_LINE_JOIN_BEVEL:
     *linejoin = 2;
     break;
     default:
     NSLog(@"ERROR Line join unknown");
     exit(-1);
     }
   */
}

- (void) DPScurrentlinewidth: (CGFloat *)width
{
  if (_ct)
    {
      *width = floatToUserSpace(ctm, cairo_get_line_width(_ct));
    }
}

- (void) DPScurrentmiterlimit: (CGFloat *)limit
{
  if (_ct)
    {
      *limit = floatToUserSpace(ctm, cairo_get_miter_limit(_ct));
    }
}

- (void) DPScurrentstrokeadjust: (int *)b
{
}

- (void) DPSsetdash: (const CGFloat *)pat : (NSInteger)size : (CGFloat)foffset
{
  if (_ct)
    {
      double doffset = doubleFromUserSpace(ctm, foffset);
      int i;
      GS_BEGINITEMBUF(dpat, size, double);

      i = size;
      while (i)
        {
          i--;
          // FIXME: When using the correct values, some dashes look wrong
          dpat[i] = doubleFromUserSpace(ctm, pat[i]) * 1.4;
        }
      cairo_set_dash(_ct, dpat, size, doffset);
      GS_ENDITEMBUF();
    }
}

- (void) DPSsetflat: (CGFloat)flatness
{
  [super DPSsetflat: flatness];
  if (_ct)
    {
      // Divide GNUstep flatness by 2 to get Cairo tolerance - this produces
      // results visually similar to OS X.
      cairo_set_tolerance(_ct, flatness / 2);
    }
}

- (void) DPSsetlinecap: (int)linecap
{
  if (_ct)
    {
      cairo_set_line_cap(_ct, (cairo_line_cap_t)linecap);
    }
}

- (void) DPSsetlinejoin: (int)linejoin
{
  if (_ct)
    {
      cairo_set_line_join(_ct, (cairo_line_join_t)linejoin);
    }
}

- (void) DPSsetlinewidth: (CGFloat)width
{
  if (_ct)
    {
      cairo_set_line_width(_ct, doubleFromUserSpace(ctm, width));
    }
}

- (void) DPSsetmiterlimit: (CGFloat)limit
{
  if (_ct)
    {
      cairo_set_miter_limit(_ct, doubleFromUserSpace(ctm, limit));
    }
}

- (void) DPSsetstrokeadjust: (int)b
{
}

/*
 * Path operations
 */

- (void) _setPath
{
  NSInteger count = [path elementCount];
  NSInteger i;
  SEL elmsel = @selector(elementAtIndex:associatedPoints:);
  NSBezierPathElement (*elmidx)(id, SEL, NSInteger, NSPoint*) =
    (NSBezierPathElement (*)(id, SEL, NSInteger, NSPoint*))[path methodForSelector: elmsel];

  // reset current cairo path
  cairo_new_path(_ct);
  for (i = 0; i < count; i++) 
    {
      NSBezierPathElement type;
      NSPoint points[3];

      type = (NSBezierPathElement)(*elmidx)(path, elmsel, i, points);
      switch(type) 
        {
          case NSMoveToBezierPathElement:
            cairo_move_to(_ct, points[0].x, points[0].y);
            break;
          case NSLineToBezierPathElement:
            cairo_line_to(_ct, points[0].x, points[0].y);
            break;
          case NSCurveToBezierPathElement:
            cairo_curve_to(_ct, points[0].x, points[0].y, 
                           points[1].x, points[1].y, 
                           points[2].x, points[2].y);
            break;
          case NSClosePathBezierPathElement:
            cairo_close_path(_ct);
            break;
          default:
            break;
        }
    }
  cairo_set_antialias(_ct, [self shouldAntialias] ? CAIRO_ANTIALIAS_DEFAULT : CAIRO_ANTIALIAS_NONE);
}

/* Keep opaque UI fills and centered images on the backing pixel grid.
   Other drawing geometry and print rendering retain their original bounds. */
- (BOOL) _backingPixelRect: (NSRect)rect image: (BOOL)image result: (NSRect *)result
{
  if (!_ct || ![_surface isKindOfClass:NSClassFromString(@"WaylandCairoShmSurface")]) return NO;
  if (!image && (rect.origin.x != floor(rect.origin.x) || rect.origin.y != floor(rect.origin.y) ||
      rect.size.width != floor(rect.size.width) || rect.size.height != floor(rect.size.height))) return NO;
  double sx, sy, dx, dy;
  cairo_surface_t *target = cairo_get_target(_ct);
  cairo_surface_get_device_scale(target, &sx, &sy);
  if (image ? (sx == 1 && sy == 1) : (sx == floor(sx) && sy == floor(sy))) return NO;
  cairo_surface_get_device_offset(target, &dx, &dy);
  NSAffineTransformStruct t = [ctm transformStruct];
  cairo_matrix_t view, device, combined, inverse;
  cairo_matrix_init(&view, t.m11, t.m12, t.m21, t.m22, t.tX, t.tY);
  cairo_get_matrix(_ct, &device);
  cairo_matrix_multiply(&combined, &view, &device);
  if (!((fabs(combined.xx) == 1 && fabs(combined.yy) == 1 && combined.xy == 0 && combined.yx == 0) ||
        (fabs(combined.xy) == 1 && fabs(combined.yx) == 1 && combined.xx == 0 && combined.yy == 0)) ||
      (!image && (combined.x0 != floor(combined.x0) || combined.y0 != floor(combined.y0)))) return NO;
  inverse = combined;
  if (cairo_matrix_invert(&inverse) != CAIRO_STATUS_SUCCESS) return NO;
  double x1 = rect.origin.x, y1 = rect.origin.y;
  double x2 = x1 + rect.size.width, y2 = y1 + rect.size.height;
  cairo_matrix_transform_point(&combined, &x1, &y1);
  cairo_matrix_transform_point(&combined, &x2, &y2);
  if (image) {
    double left = floor(fmin(x1, x2) * sx + dx + 0.5);
    double top = floor(fmin(y1, y2) * sy + dy + 0.5);
    double width = floor(fabs(x2 - x1) * sx + 0.5);
    double height = floor(fabs(y2 - y1) * sy + 0.5);
    x1 = (left - dx) / sx; x2 = (left + width - dx) / sx;
    y1 = (top - dy) / sy; y2 = (top + height - dy) / sy;
  } else {
    x1 = (floor(x1 * sx + dx + 0.5) - dx) / sx;
    x2 = (floor(x2 * sx + dx + 0.5) - dx) / sx;
    y1 = (floor(y1 * sy + dy + 0.5) - dy) / sy;
    y2 = (floor(y2 * sy + dy + 0.5) - dy) / sy;
  }
  cairo_matrix_transform_point(&inverse, &x1, &y1);
  cairo_matrix_transform_point(&inverse, &x2, &y2);
  *result = image ? NSMakeRect(fmin(x1, x2), fmin(y1, y2), fabs(x2 - x1), fabs(y2 - y1)) :
    NSMakeRect(x1, y1, x2 - x1, y2 - y1);
  return YES;
}

- (NSRect) _nativePixelRect: (NSRect)rect
{
  NSRect aligned;
  return [self _backingPixelRect:rect image:NO result:&aligned] ? aligned : rect;
}

- (BOOL) GSBackingAlignedRect: (NSRect)rect result: (NSRect *)result
{
  return [self _backingPixelRect:rect image:YES result:result];
}

- (void) DPSrectclip: (CGFloat)x : (CGFloat)y : (CGFloat)w : (CGFloat)h
{
  NSRect rect = [self _nativePixelRect:NSMakeRect(x, y, w, h)];
  [super DPSrectclip:rect.origin.x :rect.origin.y :rect.size.width :rect.size.height];
}

- (void) DPSrectfill: (CGFloat)x : (CGFloat)y : (CGFloat)w : (CGFloat)h
{
  NSRect rect = [self _nativePixelRect:NSMakeRect(x, y, w, h)];
  [super DPSrectfill:rect.origin.x :rect.origin.y :rect.size.width :rect.size.height];
}

- (void) DPSclip
{
  if (_ct)
    {
      [self _setPath];
      cairo_clip(_ct);
     }
}

- (void) DPSeoclip
{
  if (_ct)
    {
      [self _setPath];
      cairo_set_fill_rule(_ct, CAIRO_FILL_RULE_EVEN_ODD);
      cairo_clip(_ct);
      cairo_set_fill_rule(_ct, CAIRO_FILL_RULE_WINDING);
    }
}

- (void) DPSeofill
{
  if (!_ct) { [self DPSnewpath]; return; }
  cairo_fill_rule_t previous = cairo_get_fill_rule(_ct);
  cairo_set_fill_rule(_ct, CAIRO_FILL_RULE_EVEN_ODD);
  @try { [self DPSfill]; }
  @finally { cairo_set_fill_rule(_ct, previous); }
}

- (void) DPSfill
{
  if (_ct) {
    if (pattern == nil) {
      device_color_t color = fillColor;
      gsColorToRGB(&color);
      cairo_set_source_rgba(_ct, color.field[0], color.field[1], color.field[2], color.field[AINDEX]);
    }
    [self _setPath];
    cairo_fill(_ct);
  }
  [self DPSnewpath];
}

- (void) DPSinitclip
{
  if (_ct)
    {
      cairo_reset_clip(_ct);
    }
}

- (void) DPSstroke
{
  if (_ct)
    {
      BOOL zeroLineWidth = NO;
      device_color_t c;

      c = strokeColor;
      gsColorToRGB(&c);
      // The underlying concept does not allow to determine if alpha is set or not.
      cairo_set_source_rgba(_ct, c.field[0], c.field[1], c.field[2], c.field[AINDEX]);
      [self _setPath];

      // If the line width is 0, draw a thin line.
      // cairo (and Quartz) will draw nothing with a line width of 0.
      // See the PostScript Language Reference, 3rd ed, p. 674
      if (cairo_get_line_width(_ct) == 0)
	{
	  double w1 = 1.0;
	  double w2 = 1.0;
	  cairo_device_to_user_distance(_ct, &w1, &w2);
	  cairo_set_line_width(_ct, w1);
	  zeroLineWidth = YES;
	}

      cairo_stroke(_ct);

      if (zeroLineWidth)
	{
	  cairo_set_line_width(_ct, 0);
	}
    }
  [self DPSnewpath];
}

- (NSDictionary *) GSReadRect: (NSRect)r
{
  static NSDictionary *baseDict = nil;
  NSMutableDictionary *dict;
  NSSize ssize;
  NSAffineTransform *matrix;
  double x, y;
  int ix, iy;
  cairo_format_t format = CAIRO_FORMAT_ARGB32;
  cairo_surface_t *surface;
  cairo_surface_t *isurface;
  cairo_t *ct;
  cairo_status_t status;
  int dataSize;
  NSMutableData *data;
  unsigned char *dataBytes;
  uint32_t *dataPixel;
  int pixelCounter;

  if (!_ct)
    {
      return nil;
    }

  r = [ctm rectInMatrixSpace: r];
  x = NSWidth(r);
  y = NSHeight(r);
  ix = fabs(floor(x));
  iy = fabs(floor(y));
  ssize = NSMakeSize(ix, iy);

  if (!baseDict)
    {
        baseDict = [[NSDictionary dictionaryWithObjectsAndKeys:
                                    NSDeviceRGBColorSpace, @"ColorSpace",
                                    [NSNumber numberWithUnsignedInt: 8], @"BitsPerSample",
                                    [NSNumber numberWithUnsignedInt: 32], @"Depth",
                                    [NSNumber numberWithUnsignedInt: 4], @"SamplesPerPixel",
                                    [NSNumber numberWithUnsignedInt: 1], @"HasAlpha",
                                    nil]
                            retain];
    }
    
  dict = [NSMutableDictionary dictionaryWithDictionary: baseDict];

  [dict setObject: [NSValue valueWithSize: ssize] forKey: @"Size"];

  matrix = [self GSCurrentCTM];
  [matrix translateXBy: -r.origin.x - offset.x 
	  yBy: r.origin.y + NSHeight(r) - offset.y];
  [dict setObject: matrix forKey: @"Matrix"];

  dataSize = ix*iy*4;
  data = [NSMutableData dataWithLength: dataSize];
  if (data == nil)
    return nil;
  dataBytes = [data mutableBytes];

  surface = cairo_get_target(_ct);
  isurface = cairo_image_surface_create_for_data(dataBytes, format, ix, iy, 4*ix);
  status = cairo_surface_status(isurface);
  if (status != CAIRO_STATUS_SUCCESS)
    {
      NSLog(@"Cairo status '%s' in GSReadRect", cairo_status_to_string(status));
      return nil;
    }

  ct = cairo_create(isurface);
  status = cairo_status(ct);
  if (status != CAIRO_STATUS_SUCCESS)
    {
      NSLog(@"Cairo status '%s' in GSReadRect", cairo_status_to_string(status));
      cairo_surface_destroy(isurface);
      return nil;
    }

  if (_surface != nil)
    {
      ssize = [_surface size];
    }
  else 
    {
      ssize = NSMakeSize(0, 0);
    }
  cairo_set_source_surface(ct, surface, -r.origin.x, 
                           -ssize.height + r.size.height + r.origin.y);
  cairo_rectangle(ct, 0, 0, ix, iy);
  cairo_paint(ct);
  cairo_destroy(ct);
  cairo_surface_destroy(isurface);

  dataPixel = (uint32_t *) dataBytes;
  
  pixelCounter = ix * iy;

  while (pixelCounter--)
    {
#if GS_WORDS_BIGENDIAN
        // ARGB -> RGBA
      *dataPixel = (*dataPixel << 8)        // ARGB -> RGB_
                    | (*dataPixel >> 24);   // ARGB -> ___A
#else
        // ARGB -> ABGR
      *dataPixel = ((*dataPixel & 0x000000FF) << 16)    // ___B -> _B__
                    | ((*dataPixel & 0x00FF0000) >> 16) // _R__ -> ___R
                    | (*dataPixel & 0xFF00FF00);        // A_G_ -> A_G_
#endif

      dataPixel++; 
    }

  [dict setObject: data forKey: @"Data"];

  return dict;
}

static void
_set_op(cairo_t *ct, NSCompositingOperation op)
{
  switch (op)
    {
    case NSCompositeClear:
      cairo_set_operator(ct, CAIRO_OPERATOR_CLEAR);
      break;
    case NSCompositeCopy:
      cairo_set_operator(ct, CAIRO_OPERATOR_SOURCE);
      break;
    case NSCompositeSourceOver:
      cairo_set_operator(ct, CAIRO_OPERATOR_OVER);
      break;
    case NSCompositeSourceIn:
      cairo_set_operator(ct, CAIRO_OPERATOR_IN);
      break;
    case NSCompositeSourceOut:
      cairo_set_operator(ct, CAIRO_OPERATOR_OUT);
      break;
    case NSCompositeSourceAtop:
      cairo_set_operator(ct, CAIRO_OPERATOR_ATOP);
      break;
    case NSCompositeDestinationOver:
      cairo_set_operator(ct, CAIRO_OPERATOR_DEST_OVER);
      break;
    case NSCompositeDestinationIn:
      cairo_set_operator(ct, CAIRO_OPERATOR_DEST_IN);
      break;
    case NSCompositeDestinationOut:
      cairo_set_operator(ct, CAIRO_OPERATOR_DEST_OUT);
      break;
    case NSCompositeDestinationAtop:
      cairo_set_operator(ct, CAIRO_OPERATOR_DEST_ATOP);
      break;
    case NSCompositeXOR:
      cairo_set_operator(ct, CAIRO_OPERATOR_XOR);
      break;
    case NSCompositePlusDarker:
      // FIXME: There is no match for this operation in cairo!!!
      cairo_set_operator(ct, CAIRO_OPERATOR_SATURATE);
      break;
    case NSCompositeHighlight:
      // MacOSX 10.4 documentation maps this value onto NSCompositeSourceOver
      cairo_set_operator(ct, CAIRO_OPERATOR_OVER);
      break;
    case NSCompositePlusLighter:
      cairo_set_operator(ct, CAIRO_OPERATOR_ADD);
      break;
    default:
      cairo_set_operator(ct, CAIRO_OPERATOR_SOURCE);
    }
}

- (BOOL) GSdrawImageRep: (NSImageRep *)rep fromRect: (NSRect)source
                toRect: (NSRect)destination operation: (NSCompositingOperation)operation
              fraction: (CGFloat)fraction
{
#if BUILD_SERVER == SERVER_wayland
  double sx, sy;
  if (!_ct || ![_surface isDrawingToScreen]) return NO;
  cairo_surface_get_device_scale(cairo_get_target(_ct), &sx, &sy);
  if (sx == 1.0 && sy == 1.0) return NO;
  NSAffineTransformStruct logical = [ctm transformStruct];
  cairo_pattern_t *image = NULL;
  [drawcontext DPSgsave];
  @try {
    CairoGState *state = (CairoGState *)[(GSContext *)drawcontext currentGState];
    cairo_t *ct = state->_ct;
    NSRectClip(destination);
    double x1, y1, x2, y2;
    cairo_clip_extents(ct, &x1, &y1, &x2, &y2);
    /* Rasterize without applying fractional clip coverage twice. The original
       context retains its actual clip, including curves and even-odd holes. */
    cairo_reset_clip(ct);
    cairo_rectangle(ct, x1 - 2 / sx, y1 - 2 / sy, x2 - x1 + 4 / sx, y2 - y1 + 4 / sy);
    cairo_clip(ct);
    cairo_push_group(ct);
    NSAffineTransform *transform = [NSAffineTransform transform];
    [transform translateXBy:destination.origin.x yBy:destination.origin.y];
    [transform scaleXBy:destination.size.width / source.size.width yBy:destination.size.height / source.size.height];
    [transform translateXBy:-source.origin.x yBy:-source.origin.y];
    [transform concat];
    [rep draw];
    image = cairo_pop_group(ct);
  } @finally {
    [drawcontext DPSgrestore];
  }
  cairo_matrix_t base, placement;
  cairo_get_matrix(_ct, &base);
  cairo_matrix_init(&placement, logical.m11, logical.m12, logical.m21, logical.m22, logical.tX, logical.tY);
  cairo_path_t *previousPath = cairo_copy_path(_ct);
  cairo_save(_ct);
  cairo_transform(_ct, &placement);
  cairo_new_path(_ct);
  cairo_rectangle(_ct, destination.origin.x, destination.origin.y, destination.size.width, destination.size.height);
  cairo_clip(_ct);
  cairo_set_matrix(_ct, &base);
  cairo_set_source(_ct, image);
  cairo_pattern_destroy(image);
  _set_op(_ct, operation);
  cairo_paint_with_alpha(_ct, MAX(0, MIN(1, fraction)));
  cairo_restore(_ct);
  cairo_new_path(_ct);
  cairo_append_path(_ct, previousPath);
  cairo_path_destroy(previousPath);
  return YES;
#else
  return NO;
#endif
}

/* For debugging */
- (void) drawOrientationMarkersIn: (cairo_t *)ct
{
  cairo_rectangle(_ct, 0, 0, 20, 10);
  cairo_set_source_rgba(_ct, 0, 1, 0, 1);
  cairo_fill(_ct);
  cairo_rectangle(_ct, 0, 30, 20, 10);
  cairo_set_source_rgba(_ct, 0, 0, 1, 1);
  cairo_fill(_ct);
}

- (void) DPSimage: (NSAffineTransform *)matrix : (NSInteger)pixelsWide
		 : (NSInteger)pixelsHigh : (NSInteger)bitsPerSample 
		 : (NSInteger)samplesPerPixel : (NSInteger)bitsPerPixel
		 : (NSInteger)bytesPerRow : (BOOL)isPlanar
		 : (BOOL)hasAlpha : (NSString *)colorSpaceName
		 : (const unsigned char *const[5])data
{
  cairo_format_t format;
  NSAffineTransformStruct tstruct;
  cairo_surface_t *surface;
  unsigned char *dataRow, *reformattedData;
  int reformattedDataSize, rowCounter, columnCounter;
  uint32_t *reformattedDataPixel;
  cairo_matrix_t local_matrix;
  cairo_status_t status;

  if (!_ct)
    {
      return;
    }

  if (isPlanar || !([colorSpaceName isEqualToString: NSDeviceRGBColorSpace] ||
		    [colorSpaceName isEqualToString: NSCalibratedRGBColorSpace]))
    {
      // FIXME: Need to conmvert to something that is supported
      NSLog(@"Image format not support in cairo backend.\n colour space: %@ planar %d", colorSpaceName, isPlanar);
      return;
    }

  // default is 8 bit grayscale 
  if (!bitsPerSample)
    bitsPerSample = 8;
  if (!samplesPerPixel)
    samplesPerPixel = 1;

  // FIXME - does this work if we are passed a planar image but no hints ?
  if (!bitsPerPixel)
    bitsPerPixel = bitsPerSample * samplesPerPixel;
  if (!bytesPerRow)
    bytesPerRow = (bitsPerPixel * pixelsWide) / 8;

  /* make sure its sane - also handles row padding if hint missing */
  while ((bytesPerRow * 8) < (bitsPerPixel * pixelsWide))
    bytesPerRow++;

  reformattedDataSize = pixelsWide * pixelsHigh * sizeof(*reformattedDataPixel);

  switch (bitsPerPixel)
    {
    case 32:
      reformattedData = malloc(reformattedDataSize);
      if (!reformattedData)
        {
          NSLog(@"Could not allocate drawing space for image");
          return;
        }

      dataRow = (unsigned char *)data[0];
      reformattedDataPixel = (uint32_t *) reformattedData;

      rowCounter = pixelsHigh;

      while (rowCounter--)
        {
          uint32_t *dataPixel = (uint32_t *) dataRow;

          columnCounter = pixelsWide;

          while (columnCounter--)
            {
#if GS_WORDS_BIGENDIAN
                // RGBA (uint32) -> ARGB (uint32)
              *reformattedDataPixel++ = (*dataPixel >> 8)       // RGBA -> _RGB
                                        | (*dataPixel << 24);   // RGBA -> A___
#else
                // ABGR (uint32) -> ARGB (uint32)
              *reformattedDataPixel++ = ((*dataPixel & 0x000000FF) << 16)   // ___R -> _R__
                                        | ((*dataPixel & 0x00FF0000) >> 16) // _B__ -> ___B
                                        | (*dataPixel & 0xFF00FF00);        // A_G_ -> A_G_
#endif 
              dataPixel++;
            }

          dataRow += bytesPerRow;
        }
      format = CAIRO_FORMAT_ARGB32;
      break;
    case 24:
      reformattedData = malloc(reformattedDataSize);
      if (!reformattedData)
        {
          NSLog(@"Could not allocate drawing space for image");
          return;
        }

      dataRow = (unsigned char *)data[0];
      reformattedDataPixel = (uint32_t *) reformattedData;

      rowCounter = pixelsHigh;

      while (rowCounter--)
        {
          unsigned char *dataPixelComponent = dataRow;

          columnCounter = pixelsWide;

          while (columnCounter--)
            {
                // R,G,B (uchar[0-2]) -> _RGB (uint32)
              *reformattedDataPixel++ = (((uint32_t) dataPixelComponent[0]) << 16)  // R -> _R__
                                        | (((uint32_t) dataPixelComponent[1]) << 8) // G -> __G_
                                        | ((uint32_t) dataPixelComponent[2]);       // B -> ___B

              dataPixelComponent += 3;
            }

          dataRow += bytesPerRow;
        }
      format = CAIRO_FORMAT_RGB24;
      break;
    default:
      NSLog(@"Image format not support");
      return;
    }

  surface = cairo_image_surface_create_for_data((void*)reformattedData,
						format,
						pixelsWide,
						pixelsHigh,
						pixelsWide * sizeof(*reformattedDataPixel));
  status = cairo_surface_status(surface);
  if (status != CAIRO_STATUS_SUCCESS)
    {
      NSLog(@"Cairo status '%s' in DPSimage", cairo_status_to_string(status));
      if (reformattedData)
        {
          free(reformattedData);
        }

      return;
    }

  cairo_save(_ct);
  cairo_set_operator(_ct, CAIRO_OPERATOR_SOURCE);

  // Set the basic transformation
  tstruct =  [ctm transformStruct];
  cairo_matrix_init(&local_matrix,
		    tstruct.m11, tstruct.m12,
		    tstruct.m21, tstruct.m22, 
		    tstruct.tX, tstruct.tY);
  cairo_transform(_ct, &local_matrix);

  // add the local tranformation
  tstruct = [matrix transformStruct];
  cairo_matrix_init(&local_matrix,
		    tstruct.m11, tstruct.m12,
		    tstruct.m21, tstruct.m22, 
		    tstruct.tX, tstruct.tY);
  cairo_transform(_ct, &local_matrix);

  {
    cairo_pattern_t *cpattern;
    cairo_matrix_t source_matrix;
 
    cpattern = cairo_pattern_create_for_surface(surface);
    cairo_matrix_init_scale(&source_matrix, 1, -1);
    cairo_matrix_translate(&source_matrix, 0, -pixelsHigh);
    cairo_pattern_set_matrix(cpattern, &source_matrix);
    cairo_pattern_set_filter(cpattern, 
                             cairoFilterFromNSImageInterpolation([drawcontext imageInterpolation]));
    if (cairo_version() >= CAIRO_VERSION_ENCODE(1, 6, 0))
      {
        cairo_pattern_set_extend(cpattern, CAIRO_EXTEND_PAD);
      }
    cairo_set_source(_ct, cpattern);
    cairo_pattern_destroy(cpattern);
    cairo_rectangle(_ct, 0, 0, pixelsWide, pixelsHigh);
  }
 
  cairo_clip(_ct);
  cairo_paint(_ct);
  //[self drawOrientationMarkersIn: _ct];
  cairo_surface_destroy(surface);
  cairo_restore(_ct);

  if (reformattedData)
    {
      free(reformattedData);
    }
}

- (void) compositerect: (NSRect)aRect op: (NSCompositingOperation)op
{
  if (_ct)
    {
      NSBezierPath *oldPath = path;
      device_color_t c;

      cairo_save(_ct);

#if CAIRO_VERSION >= CAIRO_VERSION_ENCODE(1, 9, 4)
      if (GSCompositeHighlight == op)
        {
          cairo_set_operator(_ct, CAIRO_OPERATOR_DIFFERENCE);
          cairo_set_source_rgb(_ct, 1, 1, 1);
        }
      else
#endif
        {
          _set_op(_ct, op);
          
          c = fillColor;
          gsColorToRGB(&c);
          // The underlying concept does not allow to determine if alpha is set or not.
          cairo_set_source_rgba(_ct, c.field[0], c.field[1], c.field[2], c.field[AINDEX]);
        }

      // This is almost a rectclip::::, but the path stays unchanged.
      aRect = [self _nativePixelRect:aRect];
      path = [NSBezierPath bezierPathWithRect: aRect];
      [path transformUsingAffineTransform: ctm];
      [self _setPath];
      cairo_clip(_ct);
      cairo_paint(_ct);
      cairo_restore(_ct);
      path = oldPath;
    }
}

- (void) compositeGState: (CairoGState *)source 
                fromRect: (NSRect)srcRect 
                 toPoint: (NSPoint)destPoint 
                      op: (NSCompositingOperation)op
                fraction: (CGFloat)delta
{
  cairo_surface_t *src;
  NSSize ssize = NSZeroSize;
  BOOL copyOnSelf;
  /* The source rect in the source base coordinate space.
     This rect is the minimum bounding rect of srcRect. */
  NSRect srcRectInBase = NSZeroRect;
  /* The destination point in the target base coordinate space */
  NSPoint destPointInBase = NSZeroPoint;
  /* The origin of srcRectInBase */
  double minx, miny;
  /* The composited content size */
  double width, height;
  /* The adjusted destination point in the target base coordinate space */
  double x, y;
  /* Alternative source rect origin in the source current CTM */
  NSPoint srcRectAltOrigin;
  /* Alternative source rect origin in the source base coordinate space */
  NSPoint srcRectAltOriginInBase;
  /* The source rect origin in the source base coordinate space */
  NSPoint srcRectOriginInBase;
  BOOL originFlippedBetweenBaseAndSource = NO;
  /* The delta between the origins of srcRect and srcRectInBase */
  double dx, dy;
  cairo_pattern_t *cpattern;
  cairo_matrix_t source_matrix;

  NSDebugMLLog(@"CairoGState", @"self: %@\n", self);

  if (!_ct || !source->_ct)
    {
      return;
    }

  //NSLog(@"Composite surface %p source size %@ target size %@", self->_surface, NSStringFromSize([self->_surface size]), NSStringFromSize([source->_surface size]));
  src = cairo_get_target(source->_ct);
  copyOnSelf = (src == cairo_get_target(_ct));
  srcRectAltOrigin = NSMakePoint(srcRect.origin.x, srcRect.origin.y + srcRect.size.height);
  srcRectAltOriginInBase =  [source->ctm transformPoint: srcRectAltOrigin];
  srcRectOriginInBase = [source->ctm transformPoint: srcRect.origin];

  cairo_save(_ct);

  /* When the target and source are the same surface, we use the group tricks */
  if (copyOnSelf) cairo_push_group(_ct);

  cairo_new_path(_ct);
  _set_op(_ct, op); 

  //NSLog(@"Point %@", NSStringFromPoint(destPoint));

  /* Scales and/or rotates the local destination point with the current AppKit CTM */
  destPointInBase = [ctm transformPoint: destPoint];
  //NSLog(@"Point in base %@", NSStringFromPoint(destPointInBase));

  /* Scales and/or rotates the source rect and retrieves the minimum bounding
     rectangle that encloses it and makes it our source area */
  [source->ctm boundingRectFor: srcRect result: &srcRectInBase];
  //NSLog(@"Bounding rect %@ from %@", NSStringFromRect(srcRectInBase), NSStringFromRect(srcRect)); 

  /* Find whether the source rect origin in the base is the same than in the 
     source current CTM.
     We need to know the origin in the base to compute how much the source 
     bounding rect origin is shifted relatively to the closest source rect corner.
     We use this delta (dx, dy) to correctly composite from a rotated source. */
  originFlippedBetweenBaseAndSource = 
    ((srcRect.origin.y < srcRectAltOrigin.y && srcRectOriginInBase.y > srcRectAltOriginInBase.y)
    || (srcRect.origin.y > srcRectAltOrigin.y && srcRectOriginInBase.y < srcRectAltOriginInBase.y));
  if (originFlippedBetweenBaseAndSource)
    {
      srcRectOriginInBase = srcRectAltOriginInBase;
    }
  dx = srcRectOriginInBase.x - srcRectInBase.origin.x;
  dy = srcRectOriginInBase.y - srcRectInBase.origin.y;

  //NSLog(@"Point in base adjusted %@", NSStringFromPoint(NSMakePoint(destPointInBase.x - dx, destPointInBase.y - dy)));

  if (source->_surface != nil)
    {
      ssize = [source->_surface size];
    }

  if ((cairo_version() >= CAIRO_VERSION_ENCODE(1, 8, 0)) && 
      (cairo_version() <= CAIRO_VERSION_ENCODE(1, 13, 0)))
    {      
      // For cairo > 1.8 and < 1.13 we seem to need this adjustment
      srcRectInBase.origin.y -= 2 * (source->offset.y - ssize.height);
    }

  x = destPointInBase.x;
  y = destPointInBase.y;
  minx = NSMinX(srcRectInBase);
  miny = NSMinY(srcRectInBase);
  width = NSWidth(srcRectInBase);
  height = NSHeight(srcRectInBase);

  /* We respect the AppKit CTM effect on the origin 'aPoint' (see 
     -[ctm transformPoint:]), but we ignore the scaling and rotation effect on 
     the composited content and size. Which means we never rotate or scale the 
     content we composite.
     We use a pattern as a trick to simulate a target CTM change, this way we 
     don't touch the source CTM even when both source and target are identical 
     (e.g. scrolling case).
     We must use a pattern matrix that matches the AppKit base CTM set up in 
     -DPSinitgraphics to ensure no transform is applied to the source content, 
     translation adjustements related to destination point and source rect put 
     aside. */
  cpattern = cairo_pattern_create_for_surface(src);
  cairo_matrix_init_scale(&source_matrix, 1, -1);
  //cairo_matrix_translate(&source_matrix, 0,  -[_surface size].height);
  cairo_matrix_translate(&source_matrix, minx - x + dx, miny - y + dy - ssize.height);
  cairo_pattern_set_matrix(cpattern, &source_matrix);
  cairo_pattern_set_filter(cpattern, 
                           cairoFilterFromNSImageInterpolation([drawcontext imageInterpolation]));
  cairo_set_source(_ct, cpattern);
  cairo_pattern_destroy(cpattern);
  cairo_rectangle(_ct, x, y, width, height);
  cairo_clip(_ct);

  if (delta < 1.0)
    {
      cairo_paint_with_alpha(_ct, delta);
    }
  else
    {
      cairo_paint(_ct);
    }

  if (copyOnSelf)
    {
      cairo_pop_group_to_source(_ct);
      cairo_paint(_ct);
    }

  cairo_restore(_ct);
}

/** Unlike -compositeGState, -drawGSstate fully respects the AppKit CTM but 
doesn't support to use the receiver cairo target as the source. */
- (void) drawGState: (CairoGState *)source 
           fromRect: (NSRect)aRect 
            toPoint: (NSPoint)aPoint 
                 op: (NSCompositingOperation)op
           fraction: (CGFloat)delta
{
  NSAffineTransformStruct tstruct =  [ctm transformStruct];
  cairo_surface_t *src;
  double width, height;
  double x, y;
  cairo_pattern_t *cpattern;
  cairo_matrix_t local_matrix;
  cairo_matrix_t source_matrix;

  NSDebugMLLog(@"CairoGState", @"source: %@ fromRect: %@ toPoint: %@\n",
               source,
               NSStringFromRect(aRect),
               NSStringFromPoint(aPoint));
  
  if (!_ct || !source->_ct)
    {
      NSLog(@"WARNING: -drawGState called with a NULL target context (%p) or source context (%p)",
	    _ct, source->_ct);
      return;
    }

  src = cairo_get_target(source->_ct);

  cairo_save(_ct);

  cairo_new_path(_ct);
  _set_op(_ct, op);
  
  if (cairo_version() >= CAIRO_VERSION_ENCODE(1, 8, 0))
    {
      NSSize size = [source->_surface size];
      
      // For cairo > 1.8 we seem to need this adjustment
      aRect.origin.y -= 2*(source->offset.y - size.height);
    }

  x = aPoint.x;
  y = aPoint.y;
  width = NSWidth(aRect);
  height = NSHeight(aRect);

  // NOTE: We don't keep the Cairo matrix in sync with the AppKit matrix (aka 
  // -[NSGraphicsContext GSCurrentCTM])

  /* Prepare a Cairo matrix with the current AppKit CTM */
  cairo_matrix_init(&local_matrix,
		    tstruct.m11, tstruct.m12,
		    tstruct.m21, tstruct.m22, 
		    tstruct.tX, tstruct.tY);
  /* Append the local point transformation */
  cairo_matrix_translate(&local_matrix, x - aRect.origin.x, y - aRect.origin.y);
  /* Concat to the Cairo matrix created in -DPSinitgraphics, which adjusts the 
     mismatch between the Cairo top left vs AppKit bottom left origin. */
  cairo_transform(_ct, &local_matrix);

  //[self drawOrientationMarkersIn: _ct];

  cpattern = cairo_pattern_create_for_surface(src);
  cairo_matrix_init_scale(&source_matrix, 1, -1);
  cairo_matrix_translate(&source_matrix, 0, -[source->_surface size].height);
  cairo_pattern_set_matrix(cpattern, &source_matrix);
  cairo_pattern_set_filter(cpattern, 
                           cairoFilterFromNSImageInterpolation([drawcontext imageInterpolation]));
  if (cairo_version() >= CAIRO_VERSION_ENCODE(1, 6, 0))
    {
      cairo_pattern_set_extend(cpattern, CAIRO_EXTEND_PAD);
    }
  cairo_set_source(_ct, cpattern);
  cairo_pattern_destroy(cpattern);
  cairo_rectangle(_ct, aRect.origin.x, aRect.origin.y, width, height);
  cairo_clip(_ct);

  if (delta < 1.0)
    {
      cairo_paint_with_alpha(_ct, delta);
    }
  else
    {
      cairo_paint(_ct);
    }

  cairo_restore(_ct);
}

@end

@implementation CairoGState (PatternColor)

- (void *) saveClip
{
#if CAIRO_VERSION > CAIRO_VERSION_ENCODE(1, 4, 0)
  if (_ct)
    {
      cairo_status_t status;
      cairo_rectangle_list_t *clip_rects = cairo_copy_clip_rectangle_list(_ct);

      status = cairo_status(_ct);
      if (status == CAIRO_STATUS_SUCCESS)
        {
          return clip_rects;
        }
    }
#endif

  return NULL;
}

- (void) restoreClip: (void *)savedClip
{
#if CAIRO_VERSION > CAIRO_VERSION_ENCODE(1, 4, 0)
  if (_ct && savedClip)
    {
      int i;
      cairo_rectangle_list_t *clip_rects = (cairo_rectangle_list_t *)savedClip;
      
      cairo_reset_clip(_ct);
      if (cairo_version() >= CAIRO_VERSION_ENCODE(1, 6, 0))
        {
          for (i = 0; i < clip_rects->num_rectangles; i++)
            {
              cairo_rectangle_t rect = clip_rects->rectangles[i];
              
              cairo_rectangle(_ct, rect.x, rect.y, 
                              rect.width, rect.height);
              cairo_clip(_ct);
            }
        }
      else
        {
          for (i = 0; i < clip_rects->num_rectangles; i++)
            {
              cairo_rectangle_t rect = clip_rects->rectangles[i];
              NSSize size = [_surface size];
              
              cairo_rectangle(_ct, rect.x, 
                              /* This strange computation is due 
                                 to the device offset missing for 
                                 clip rects in cairo < 1.6.0.  */
                              rect.y + 2*(offset.y - size.height), 
                              rect.width, rect.height);
              cairo_clip(_ct);
            }
        }
      cairo_rectangle_list_destroy(clip_rects);
    }
#endif
}

@end

@implementation CairoGState (NSGradient)

- (void) drawGradient: (NSGradient*)gradient
           fromCenter: (NSPoint)startCenter
               radius: (CGFloat)startRadius
             toCenter: (NSPoint)endCenter 
               radius: (CGFloat)endRadius
              options: (NSUInteger)options
{
  if (_ct)
    {
      cairo_status_t status;
      int i;
      int stops = [gradient numberOfColorStops];
      NSPoint startP = [ctm transformPoint: startCenter];
      NSPoint endP = [ctm transformPoint: endCenter];
      cairo_pattern_t *cpattern = cairo_pattern_create_radial(startP.x, startP.y, 
                                                              doubleFromUserSpace(ctm, startRadius),
                                                              endP.x, endP.y, 
                                                              doubleFromUserSpace(ctm, endRadius));
      status = cairo_pattern_status(cpattern);
      if (status != CAIRO_STATUS_SUCCESS)
        {
          return;
        }

      for (i = 0; i < stops; i++)
        {
          NSColor *color;
          CGFloat location;
          double red;
          double green;
          double blue;
          double alpha;
          
          [gradient getColor: &color
                    location: &location
                     atIndex: i];
          red = [color redComponent];
          green = [color greenComponent];
          blue = [color blueComponent];
          alpha = [color alphaComponent];
          cairo_pattern_add_color_stop_rgba(cpattern, location,
                                            red, green, blue, alpha);
        }
      
      cairo_save(_ct);
      cairo_set_source(_ct, cpattern);
      cairo_pattern_destroy(cpattern);
      cairo_paint(_ct);
      cairo_restore(_ct);
    }
}

- (void) drawGradient: (NSGradient*)gradient
            fromPoint: (NSPoint)startPoint
              toPoint: (NSPoint)endPoint
              options: (NSUInteger)options
{
  if (_ct)
    {
      cairo_status_t status;
      int i;
      int stops = [gradient numberOfColorStops];
      NSPoint startP = [ctm transformPoint: startPoint];
      NSPoint endP = [ctm transformPoint: endPoint];
      cairo_pattern_t *cpattern = cairo_pattern_create_linear(startP.x, startP.y,
                                                              endP.x, endP.y);
      
      status = cairo_pattern_status(cpattern);
      if (status != CAIRO_STATUS_SUCCESS)
        {
          return;
        }

      for (i = 0; i < stops; i++)
        {
          NSColor *color;
          CGFloat location;
          double red;
          double green;
          double blue;
          double alpha;
          NSString *colorSpaceName;
	  
          [gradient getColor: &color
                    location: &location
                     atIndex: i];

	  colorSpaceName = [color colorSpaceName];
	  if([NSCalibratedRGBColorSpace isEqualToString: colorSpaceName] ||
	     [NSDeviceRGBColorSpace isEqualToString: colorSpaceName])
	    {
	      red = [color redComponent];
	      green = [color greenComponent];
	      blue = [color blueComponent];
	      alpha = [color alphaComponent];
	      cairo_pattern_add_color_stop_rgba(cpattern, location,
						red, green, blue, alpha);
	    }
	  else if([NSCalibratedWhiteColorSpace isEqualToString: colorSpaceName] ||
		  [NSDeviceWhiteColorSpace isEqualToString: colorSpaceName] ||
		  [NSCalibratedBlackColorSpace isEqualToString: colorSpaceName] ||
		  [NSDeviceBlackColorSpace isEqualToString: colorSpaceName])
	    {
	      red = [color whiteComponent];
	      green = [color whiteComponent];
	      blue = [color whiteComponent];
	      alpha = [color alphaComponent];
	      cairo_pattern_add_color_stop_rgba(cpattern, location,
						red, green, blue, alpha);
	    }
	  else
	    {
	      NSLog(@"Cannot draw gradient for %@",colorSpaceName); 
	    }
        }
      
      cairo_save(_ct);
      cairo_set_source(_ct, cpattern);
      cairo_pattern_destroy(cpattern);
      cairo_paint(_ct);
      cairo_restore(_ct);
    }
}

@end
