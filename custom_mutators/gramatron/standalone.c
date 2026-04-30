/* For AFL++ custom mutator shared library: provide default standalone flag.
 * When fuzzing inside AFL++, global_afl is set, but some helpers still check
 * gf_standalone_mode to decide fallback RNG behavior.
 */
int gf_standalone_mode = 0;
