/*
   CairoContext.m

   Copyright (C) 2003 Free Software Foundation, Inc.

   August 31, 2003
   Written by Banlu Kemiyatorn <object at gmail dot com>

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

#include <AppKit/NSBitmapImageRep.h>
#include <AppKit/NSGraphics.h>
#include <AppKit/NSPrintInfo.h>
#include <AppKit/NSPrintOperation.h>

#include "cairo/CairoContext.h"
#include "cairo/CairoSurface.h"
#include "cairo/CairoPSSurface.h"
#include "cairo/CairoPDFSurface.h"
#include "cairo/CairoFontInfo.h"
#include "cairo/CairoFontEnumerator.h"
#include "config.h"

#define CGSTATE ((CairoGState *)gstate)

#include "wayland/WaylandServer.h"
#include "cairo/CairoGState.h"
#include "cairo/WaylandCairoShmSurface.h"
#define _CAIRO_GSTATE_CLASSNAME CairoGState
#define _CAIRO_SURFACE_CLASSNAME WaylandCairoShmSurface

@implementation CairoContext

+ (void) initializeBackend
{
  [NSGraphicsContext setDefaultContextClass: self];

  [GSFontEnumerator setDefaultClass: [CairoFontEnumerator class]];
  [GSFontInfo setDefaultClass: [CairoFontInfo class]];
}

+ (Class) GStateClass
{
  return [_CAIRO_GSTATE_CLASSNAME class];
}

+ (BOOL) handlesPS
{
  return YES;
}

- (BOOL) supportsDrawGState
{
  return YES;
}

- (BOOL) GSBackingAlignedRect: (NSRect)rect result: (NSRect *)result
{
  return [CGSTATE GSBackingAlignedRect:rect result:result];
}

- (BOOL) GSdrawImageRep: (NSImageRep *)rep fromRect: (NSRect)source
                toRect: (NSRect)destination operation: (NSCompositingOperation)operation
              fraction: (CGFloat)fraction
{
  return [CGSTATE GSdrawImageRep:rep fromRect:source toRect:destination operation:operation fraction:fraction];
}

- (id) initWithContextInfo: (NSDictionary *)info
{
  self = [super initWithContextInfo: info];
  if (self)
    {
      [self setImageInterpolation: NSImageInterpolationDefault];
    }
  return self;
}

- (BOOL) isDrawingToScreen
{
  CairoSurface *surface = nil;
  [CGSTATE GSCurrentSurface: &surface : NULL : NULL];
  return [surface isDrawingToScreen];
}

- (void) flushGraphics
{
  CairoSurface *surface = nil;
  [CGSTATE GSCurrentSurface: &surface : NULL : NULL];
  [surface handleExposeRect: NSMakeRect(0, 0, [surface size].width, [surface size].height)];
}

/* Private backend methods */
+ (void) handleExposeRect: (NSRect)rect forDriver: (void *)driver
{
  if ([(id)driver isKindOfClass: [CairoSurface class]])
    [(CairoSurface *)driver handleExposeRect: rect];
}

@end 

@implementation CairoContext (Ops) 

- (BOOL) isCompatibleBitmap: (NSBitmapImageRep*)bitmap
{
  NSString *colorSpaceName;

  if ([bitmap bitmapFormat] != 0)
    {
      return NO;
    }

  if ([bitmap isPlanar])
    {
      return NO;
    }

  if ([bitmap bitsPerSample] != 8)
    {
      return NO;
    }

  colorSpaceName = [bitmap colorSpaceName];
  if (![colorSpaceName isEqualToString: NSDeviceRGBColorSpace] &&
      ![colorSpaceName isEqualToString: NSCalibratedRGBColorSpace])
    {
      return NO;
    }
  else
    {
      return YES;
    }
}

- (void) GSCurrentDevice: (void **)device : (int *)x : (int *)y
{
  CairoSurface *surface;

  [CGSTATE GSCurrentSurface: &surface : x : y];
  if (device)
    {
      *device = surface->gsDevice;
    }
}

- (void) GSSetDevice: (void *)device : (int)x : (int)y
{
  CairoSurface *surface;

  surface = [[_CAIRO_SURFACE_CLASSNAME alloc] initWithDevice: device];

  [CGSTATE GSSetSurface: surface : x : y];
  [surface release];
}

- (void) beginPrologueBBox: (NSRect)boundingBox
              creationDate: (NSString*)dateCreated
                 createdBy: (NSString*)anApplication
                     fonts: (NSString*)fontNames
                   forWhom: (NSString*)user
                     pages: (int)numPages
                     title: (NSString*)aTitle
{
  CairoSurface *surface;
  NSSize size;
  NSString *contextType;

  NSPrintOperation *printOp = [NSPrintOperation currentOperation];
  NSPrintInfo *printInfo = [printOp printInfo];
  contextType = [context_info objectForKey:
                         NSGraphicsContextRepresentationFormatAttributeName];

  if (printInfo != nil)
    {
      BOOL exporting = [printOp isEPSOperation] ||
        [contextType isEqual: NSGraphicsContextPDFFormat];
      size = exporting ? boundingBox.size : [printInfo paperSize];

      // FIXME: This is confusing..
      // When an 8.5x11 page is set to landscape,
      // NSPrintInfo also swaps the paperSize to be 11x8.5,
      // but gui also adds a 90 degree rotation as if it will
      // be drawing on a 8.5x11 page. So, swap 11x8.5 back to
      // 8.5x11 here.
      if (!exporting && [printInfo orientation] == NSLandscapeOrientation)
	{
	  size = NSMakeSize(size.height, size.width);
	}
    }
  else
    {
      [NSException raise: NSInternalInconsistencyException
		  format: @"current print operation printInfo is nil in %@",
		   NSStringFromSelector(_cmd)];
      return;
    }

  if (contextType)
    {
      if ([contextType isEqual: NSGraphicsContextPSFormat])
        {
          surface = [[CairoPSSurface alloc] initWithDevice: context_info];
          [surface setSize: size];
          // This strange setting is needed because of the way GUI handles offset.
          [CGSTATE GSSetSurface: surface : 0.0 : size.height];
          RELEASE(surface);
        }
      else if ([contextType isEqual: NSGraphicsContextPDFFormat])
        {
          surface = [[CairoPDFSurface alloc] initWithDevice: context_info];
          [surface setSize: size];
          // This strange setting is needed because of the way GUI handles offset.
          [CGSTATE GSSetSurface: surface : 0.0 : size.height];
          RELEASE(surface);
        }
    }
}

- (void) showPage
{
  [CGSTATE showPage];
}

@end

#undef _CAIRO_SURFACE_CLASSNAME
#undef _CAIRO_GSTATE_CLASSNAME

