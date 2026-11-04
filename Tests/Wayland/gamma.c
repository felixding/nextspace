/* Check the native LUT contract through wlroots output-state storage. MIT. */
#include <assert.h>
#include <string.h>
#include "../../Applications/Compositor/src/output-gamma.h"

int main(void)
{
  struct wlr_output_state state;
  wlr_output_state_init(&state);
  struct output_gamma identity = {1, 1, 1, 1};
  assert(!output_gamma_state(&state, 0, identity));
  assert(!output_gamma_state(&state, 1, identity));
  assert(!output_gamma_state(&state, 65537, identity));
  assert(!(state.committed & WLR_OUTPUT_STATE_GAMMA_LUT));
  assert(output_gamma_state(&state, 5, identity));
  const uint16_t linear[] = {0, 16383, 32767, 49151, 65535};
  for (size_t channel = 0; channel < 3; channel++)
    assert(memcmp(state.gamma_lut + channel * 5, linear, sizeof(linear)) == 0);
  struct output_gamma adjusted = {0.5, 1, 2, 0.75};
  assert(output_gamma_state(&state, 5, adjusted));
  assert(state.gamma_lut[1] == 24575);  /* sqrt(1/4) * 3/4 */
  assert(state.gamma_lut[6] == 12287);  /* (1/4) * 3/4 */
  assert(state.gamma_lut[11] == 3071);  /* (1/4)^2 * 3/4 */
  for (size_t channel = 0; channel < 3; channel++) {
    assert(state.gamma_lut[channel * 5] == 0);
    assert(state.gamma_lut[channel * 5 + 4] == 49151);
  }
  uint16_t previous[15]; memcpy(previous, state.gamma_lut, sizeof(previous));
  struct output_gamma invalid[] = {{NAN,1,1,1}, {1,INFINITY,1,1}, {1,1,0,1},
    {1,1,-1,1}, {1,1,11,1}, {1,1,1,-0.1}, {1,1,1,2.1}};
  for (size_t i = 0; i < sizeof(invalid) / sizeof(*invalid); i++) {
    assert(!output_gamma_state(&state, 5, invalid[i]));
    assert(memcmp(previous, state.gamma_lut, sizeof(previous)) == 0);
  }
  assert(output_gamma_state(&state, 257, (struct output_gamma){1,1,1,2}));
  assert(state.gamma_lut[0] == 0 && state.gamma_lut[128] == UINT16_MAX);
  for (size_t channel = 0; channel < 3; channel++)
    for (size_t i = 1; i < 257; i++)
      assert(state.gamma_lut[channel * 257 + i] >= state.gamma_lut[channel * 257 + i - 1]);
  assert(output_gamma_state(&state, 257, (struct output_gamma){1,1,1,0}));
  for (size_t i = 0; i < 3 * 257; i++) assert(state.gamma_lut[i] == 0);
  wlr_output_state_finish(&state);
  return 0;
}
