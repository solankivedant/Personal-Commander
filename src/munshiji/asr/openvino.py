"""OpenVINO IR backend for Whisper on Intel iGPU (optimum-intel / whisper.cpp).
Phase 6 hardware optimization.

Phase 0 finding (docs/PHASE-0-RESULTS.md), don't rediscover this the hard way:
OpenVINO's speedup is NOT automatic from converting to IR format. The default
device is CPU, which measured *no faster* than the plain ctranslate2 CPU
backend (~2.9s for a ~3s clip on the target i7-1355U). You must explicitly
pass device="GPU" to target the Iris Xe iGPU — doing so cut latency to ~850ms
(3.4x). That was still ~40% over the 600ms gate; INT8 quantization (NNCF /
OVQuantizer) of the IR was identified as the next lever and was not yet
attempted as of that spike. Whichever of you picks this up: try that before
concluding `small` can't hit the target on this hardware.
"""
