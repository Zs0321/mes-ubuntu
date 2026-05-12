---
name: qr-label-to-mes-query
description: Use when a DingTalk MES bot needs to read QR-label images, extract serial numbers or product names, match products by serial prefix, and query MES records for each detected serial.
---

# QR Label To MES Query

## Overview
This skill describes the image-to-query flow used by the DingTalk MES bot.

Use it when the bot receives a label photo and must:
- download the DingTalk image
- recognize serial numbers or product names from the label
- match the product by QR prefix rule
- query MES data for every detected serial number
- return a Chinese summary to the DingTalk group

## When to Use
- The message contains a DingTalk downloadCode
- The user asks questions such as image process lookup or image serial lookup
- The bot needs to process one image with one or more QR labels
- Prefix matching must use MES project config data instead of guessing by product name

Do not use this skill for pure text FAQ or simple non-image chat.

## End-To-End Flow
1. Parse the DingTalk message and collect all downloadCode values from picture or 
ichText content.
2. Download the original image with DingTalk robot APIs.
3. Send the image to the vision model qwen/qwen3-vl-30b.
4. Extract:
   - serial_numbers
   - product_type_names
   - 
aw_qr_texts
   - optional 
otes
5. For each detected serial number:
   - resolve MES prefix rules from project_configs.db
   - choose the longest matching prefix
   - call MES API to query the real record for the full serial number
6. Build one reply section per serial number.
7. If FAQ or text query already answers the message, do that first. Image flow is only for messages that actually contain image download codes.

## Model Split
- Vision model: qwen/qwen3-vl-30b
  Use for QR-label recognition and extracting serial numbers from images.
- Text model: qwen3.5-35b-a3b
  Use for Chinese fallback answers when FAQ and MES query logic do not match.

## Data Sources
- Prefix matching database:
  /volume2/MES/QRMES/projects/project_configs.db
- MES API base:
  http://127.0.0.1:8891
- DingTalk image download:
  https://api.dingtalk.com/v1.0/robot/messageFiles/download

## Prefix Matching Rule
- Match by serial prefix, not by product model name.
- Normalize and compare the full detected serial text.
- Prefer the longest matching prefix.
- If multiple serial numbers are found in one image, query all of them.
- If no serial number is found, only return recognition results and ask for a clearer image if needed.

## Reply Strategy
- Always answer in Chinese.
- Show how many serial numbers were recognized.
- Return results one serial number at a time.
- For each serial:
  - prefix-matched project or product
  - whether MES record exists
  - quality summary
  - process summary

## Failure Handling
- If image download fails:
  return a clear Chinese error and ask the user to resend a clearer image.
- If the vision model finds no serial:
  return recognized product names or raw QR text only.
- If prefix matching fails:
  say the serial did not hit any configured product prefix.
- If MES API has no record:
  say the database record was not found, but still include the prefix match result if available.

## Key Files
- dingtalk_mes_bot/message_parser.py
- dingtalk_mes_bot/handlers/router.py
- dingtalk_mes_bot/services/dingtalk_image_service.py
- dingtalk_mes_bot/services/vision_recognition_service.py
- dingtalk_mes_bot/services/project_prefix_service.py
- dingtalk_mes_bot/services/mes_query_service.py
- dingtalk_mes_bot/services/image_query_service.py
- dingtalk_mes_bot/services/llm_answer_service.py

## Quick Verification
- Send a richText DingTalk message with one image and @机器人.
- Confirm the runtime log shows the image message was received.
- Confirm the reply includes serial-by-serial results.
- Test:
  - one serial in one label
  - multiple serials in one image
  - image only
  - image plus extra text
