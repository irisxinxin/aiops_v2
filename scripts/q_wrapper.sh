#!/bin/bash
# Q CLI wrapper script

export NO_COLOR=1
export CLICOLOR=0
export TERM=dumb

exec /home/ubuntu/.local/bin/q "$@"
