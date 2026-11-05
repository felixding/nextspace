# Copy into an isolated build tree without reusing objects from the checkout.
copy_sources()
{
  mkdir -p "$2"
  cp -R "$1/." "$2/"
  find "$2" -type d \( -name obj -o -name .wayland-generated \) -prune -exec rm -rf {} +
}
