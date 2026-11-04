/* Native output ramps use the existing SystemKit power-curve convention. MIT. */
#ifndef NEXTSPACE_OUTPUT_GAMMA_H
#define NEXTSPACE_OUTPUT_GAMMA_H
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <wlr/types/wlr_output.h>

struct output_gamma { double red, green, blue, brightness; };

static bool output_gamma_valid(struct output_gamma gamma)
{
  return isfinite(gamma.red) && gamma.red >= 0.1 && gamma.red <= 10 &&
    isfinite(gamma.green) && gamma.green >= 0.1 && gamma.green <= 10 &&
    isfinite(gamma.blue) && gamma.blue >= 0.1 && gamma.blue <= 10 &&
    isfinite(gamma.brightness) && gamma.brightness >= 0 && gamma.brightness <= 2;
}

static bool output_gamma_state(struct wlr_output_state *state, size_t size,
    struct output_gamma gamma)
{
  if (size < 2 || size > 65536 || !output_gamma_valid(gamma)) return false;
  uint16_t *ramps = malloc(3 * size * sizeof(*ramps));
  if (!ramps) return false;
  double channels[] = {gamma.red, gamma.green, gamma.blue};
  for (size_t channel = 0; channel < 3; channel++)
    for (size_t i = 0; i < size; i++)
      ramps[channel * size + i] = fmin(pow((double)i / (size - 1), channels[channel]) *
        gamma.brightness, 1) * UINT16_MAX;
  bool ok = wlr_output_state_set_gamma_lut(state, size, ramps, ramps + size, ramps + 2 * size);
  free(ramps);
  return ok;
}
#endif
