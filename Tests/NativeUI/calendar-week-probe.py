#!/usr/bin/env python3
"""Pinned GNUstep/ICU week-policy semantic witnesses against Python's ISO dates.

Usage: calendar-week-probe.py <Base-library> <results.json> [--require]
Run with LD_LIBRARY_PATH containing /Library/Libraries and /usr/NextSpace/lib.
The optional --require distinguishes the recorded negative baseline from a gate.
"""
import ctypes as C,json,sys,ctypes.util
from pathlib import Path
from datetime import datetime,timezone
C.CDLL(sys.argv[1],mode=C.RTLD_GLOBAL)
r=C.CDLL('/usr/NextSpace/lib/libobjc.so.4.6');r.objc_getClass.argtypes=[C.c_char_p];r.objc_getClass.restype=C.c_void_p;r.sel_registerName.argtypes=[C.c_char_p];r.sel_registerName.restype=C.c_void_p;r.objc_msg_lookup.argtypes=[C.c_void_p,C.c_void_p];r.objc_msg_lookup.restype=C.c_void_p
def cls(name):return r.objc_getClass(name.encode())
def send(obj,name,types=(),args=(),rest=C.c_void_p):
 sel=r.sel_registerName(name.encode());return C.CFUNCTYPE(rest,C.c_void_p,C.c_void_p,*types)(r.objc_msg_lookup(obj,sel))(obj,sel,*args)
pool=send(cls('NSAutoreleasePool'),'new')
def text(value):return send(cls('NSString'),'stringWithUTF8String:',(C.c_char_p,),(value.encode(),))
tz=send(cls('NSTimeZone'),'timeZoneForSecondsFromGMT:',(C.c_long,),(0,));rows=[]

cal=send(cls('NSCalendar'),'calendarWithIdentifier:',(C.c_void_p,),(text('gregorian'),))
send(cal,'setLocale:',(C.c_void_p,),(send(cls('NSLocale'),'localeWithLocaleIdentifier:',(C.c_void_p,),(text('en_US_POSIX'),)),),None)
send(cal,'setTimeZone:',(C.c_void_p,),(tz,),None)
send(cal,'setGregorianStartDate:',(C.c_void_p,),(send(cls('NSDate'),'dateWithTimeIntervalSince1970:',(C.c_double,),(-8640000000000.,)),),None)
for name,value in [('setFirstWeekday:',2),('setMinimumDaysInFirstWeek:',4)]:send(cal,name,(C.c_ulong,),(value,),None)
lib=C.util.find_library('icui18n');icu=C.CDLL(lib);limit=getattr(icu,'ucal_getLimit_'+lib.rsplit('.',1)[1]);limit.argtypes=[C.c_void_p,C.c_int,C.c_int,C.POINTER(C.c_int)];limit.restype=C.c_int
class Range(C.Structure):_fields_=[('location',C.c_ulong),('length',C.c_ulong)]
for stamp in ['0001-01-01','1500-01-01','1582-10-01','1969-12-29','2020-12-28','2021-01-01','2021-01-04','2026-12-28','2027-01-01','2027-01-04']:
 d=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc);seconds=d.timestamp();year,week,weekday=d.isocalendar();date=send(cls('NSDate'),'dateWithTimeIntervalSince1970:',(C.c_double,),(seconds,))
 parts=send(cal,'components:fromDate:',(C.c_ulong,C.c_void_p),((1<<14)|(1<<13)|(1<<9),date))
 observed={k:send(parts,k,rest=C.c_long) for k in ['yearForWeekOfYear','weekOfYear','weekday']}
 rebuilt=send(cal,'dateFromComponents:',(C.c_void_p,),(parts,));actual=send(rebuilt,'timeIntervalSince1970',rest=C.c_double)
 error=C.c_int(0);native=send(cal,'_UCalendar');maximum=limit(native,3,5,C.byref(error))
 measured=send(cal,'rangeOfUnit:inUnit:forDate:',(C.c_ulong,C.c_ulong,C.c_void_p),(1<<13,1<<14,date),rest=Range)
 expected_count=datetime(year,12,28).isocalendar().week
 row=dict(range=[measured.location,measured.length],range_passed=measured.location==1 and measured.length==expected_count,expected_count=expected_count,date=stamp,seconds=seconds,expected_year=year,expected_week=week,observed=observed,constructed=actual,construction_passed=actual==seconds,ICU_week_count=maximum,ICU_error=error.value);rows.append(row);print(json.dumps(row),flush=True)
Path(sys.argv[2]).write_text(json.dumps(rows,indent=2)+'\n');send(pool,'drain',rest=None)

if '--require' in sys.argv:
 assert len(rows)==10 and all(x['construction_passed'] and x['range_passed'] and x['ICU_week_count']==x['expected_count'] and x['observed']['yearForWeekOfYear']==x['expected_year'] and x['observed']['weekOfYear']==x['expected_week'] for x in rows)
 print(json.dumps(dict(passed=40)))
