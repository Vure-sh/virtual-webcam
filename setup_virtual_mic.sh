#!/usr/bin/env bash
# ==============================================================================
# Setup Virtual Microphone Audio Sink for Discord (PipeWire / PulseAudio)
# ==============================================================================

set -e
if pactl list modules short | grep -q "sink_name=VirtualMic"; then
    echo "✓ Virtual Microphone sink is already active."
else
    echo "Creating Virtual Microphone sink..."
    pactl load-module module-null-sink sink_name=VirtualMic sink_properties=device.description="Virtual_Microphone"
    echo "✓ Virtual Microphone created!"
fi

echo ""
echo "🎙️ How to send sound to Discord:"
echo "1. In Discord: Go to Settings -> Voice & Video -> Input Device (Microphone)."
echo "2. Select 'Virtual_Microphone' (or Monitor of Virtual_Microphone)."
echo "3. Play video with sound enabled in Virtual Webcam!"
