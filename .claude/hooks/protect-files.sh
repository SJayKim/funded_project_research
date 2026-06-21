#!/bin/bash
INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path')
if [[ "$FILE" == *.env* ]] || [[ "$FILE" == *secret* ]] || \
   [[ "$FILE" == *.pem ]] || [[ "$FILE" == *.key ]]; then
  echo "Blocked: protected file ($FILE)" >&2
  exit 2
fi
exit 0
