/* Native action receipts and scoped application binding data, not checkbox
 * state rules or widget behavior. Include after Transport.inc. GPL-2.0-or-later. */
struct NXSControlAction {uint32_t epoch;int state,ready;};
struct NXSCheckboxActivation {uint64_t node,control;struct NXSControlAction action;int armed;};
static __thread struct NXSCheckboxActivation native_checkbox_activation;
static int native_control_action_snapshot(const struct NXSResponse *response,double before,struct NXSControlAction *action)
{
  *action=(struct NXSControlAction){0};
  if(!response||!isfinite(before)||before<0||response->parts[0].y||!isfinite(response->parts[0].width)||response->parts[0].width<=before||
     !isfinite(response->parts[0].height)||response->parts[0].height< -1||response->parts[0].height>1||
     response->parts[0].height!=trunc(response->parts[0].height))return 0;
  *action=(struct NXSControlAction){atomic_load(&native_host_epoch),(int)response->parts[0].height,1};return 1;
}
static int native_control_action_valid(const struct NXSControlAction *action)
{return action->ready&&action->epoch==atomic_load(&native_host_epoch);}
static struct NXSCheckboxActivation native_checkbox_enter(uint64_t node,uint64_t control,struct NXSControlAction action)
{
  struct NXSCheckboxActivation previous=native_checkbox_activation;
  native_checkbox_activation=(struct NXSCheckboxActivation){node,control,action,node&&control&&native_control_action_valid(&action)};
  return previous;
}
