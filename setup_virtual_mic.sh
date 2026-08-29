#!/usr/bin/env bash
# ==============================================================================
# Setup Virtual Microphone Audio Device for Discord (PipeWire / PulseAudio)
# ==============================================================================

set -e

# Unload any stale VirtualMic modules first to avoid duplicates
for mod in $(pactl list modules short 2>/dev/null | grep -i VirtualMic | cut -f1); do
    pactl unload-module "$mod" 2>/dev/null || true
done

echo "1. Creating Virtual Audio Sink..."
pactl load-module module-null-sink sink_name=VirtualMic sink_properties=device.description="Virtual_Audio_Sink"

echo "2. Creating Virtual Microphone Source (shows as input in Discord)..."
pactl load-module module-remap-source master=VirtualMic.monitor source_name=VirtualMic_Source source_properties=device.description="Virtual_Microphone"

echo "3. Boosting virtual mic sink volume to 150%..."
pactl set-sink-volume VirtualMic 150% 2>/dev/null || true

echo ""
echo "=========================================================================="
echo "✓ Virtual Microphone created successfully!"
echo "=========================================================================="
echo "🎙️ In Discord:"
echo "   1. Go to User Settings (⚙️) -> Voice & Video -> Input Device (Microphone)"
echo "   2. Select: 'Virtual_Microphone'"
echo "   3. Important: Under 'Voice Processing', turn OFF 'Noise Suppression (Krisp)'"
echo "      and 'Echo Cancellation' so Discord doesn't filter out video sound!"
echo "=========================================================================="
