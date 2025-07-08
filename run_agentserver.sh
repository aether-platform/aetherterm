#!/bin/bash
export AI_PROVIDER=lmstudio
export LMSTUDIO_URL=http://192.168.210.218:1234
export AETHERTERM_AI_PROVIDER=lmstudio
cd /mnt/c/workspace/vibecoding-platform/app/terminal
exec uv run aetherterm-agentserver --host=localhost --port=57575 --unsecure --debug