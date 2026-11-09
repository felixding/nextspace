/* Original Blink month/date conversion, with ABI data adaptation only.
 * No month parser, calendar arithmetic or native control lives here. */
#include "pinned-months.h"
static int month_type(const void *type)
{return forms_months_enabled&&type&&*(const uintptr_t *)type==base+NXS_MONTH_TYPE_VTABLE+16;}
struct BlinkDateComponents {
  int millisecond,second,minute,hour,day,month,year,week,type;
};
struct BlinkMonthDecimal {uint64_t opaque[3];};
_Static_assert(sizeof(struct BlinkDateComponents)==36&&sizeof(struct BlinkMonthDecimal)==24,
  "Pinned original date/decimal model layouts");
static int month_number(void *type,double seconds,double *number)
{
  struct BlinkDateComponents parts={0};
  /* The original full converter includes HTML date limits and validation. */
  if(!((int (*)(void *,double))(base+NXS_MONTH_DATE_COMPONENTS))(&parts,seconds*1000.))return 0;
  parts.type=3; /* Original DateComponents::kMonth; date components stay native. */
  void *serialized=((void *(*)(const void *,int))(base+NXS_MONTH_COMPONENTS_STRING))(&parts,0);
  struct BlinkMonthDecimal fallback=((struct BlinkMonthDecimal (*)(double))(base+NXS_MONTH_DECIMAL_FROM_DOUBLE))(NAN);
  struct BlinkMonthDecimal parsed=((struct BlinkMonthDecimal (*)(void *,const void *,const void *))
    (base+NXS_MONTH_PARSE_NUMBER))(type,&serialized,&fallback);
  *number=((double (*)(const void *))(base+NXS_MONTH_DECIMAL_TO_DOUBLE))(&parsed);
  ((void (*)(void *))(base+0x7246038))(&serialized);return isfinite(*number);
}
