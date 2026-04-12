# Task: Fix channel selection and visualize channel on the dashboard

## Bug to Fix
* **`pipeline/campaigns/campaign_engine.py` (line ~243)**: The dictionary returned by `generate_pre_arrival()` includes `avg_length_stay` (average length of stay) but is missing `avg_booking_leadtime` (average booking lead time; tiempo de espera entre reserva y estancia). Add it as follows:
    ```python
    "avg_booking_leadtime": float(user_rows["AVG_BOOKING_LEADTIME"].iloc[0]),
    ```
* **`autonomous/campaign_generator.py` (line 338)**: It currently passes `avg_length_stay` to the `channel_selector` (channel selector; módulo de selección de canal) instead of `avg_booking_leadtime`.
    * **Before (incorrect)**: `{"avg_booking_leadtime": campaign_data.get("avg_length_stay", 15)}`
    * **After**: `{"avg_booking_leadtime": campaign_data.get("avg_booking_leadtime", 15)}`

**Expected Outcome**: With this change, approximately 48 users with a leadtime < 7 days will receive `primary_channel: "sms"`, and 82 young users will receive `"push"`, preventing the system from defaulting to email for all cases.

## Channel Visualization in the Frontend
In **`frontend/marketing/app.js`**, within the `renderCampaignDone()` function: the `ev.channel` event already arrives with `{primary_channel, secondary_channel, reason}`. Update the campaign card:

1.  **Channel Badge (distintivo visual)**: Add a badge with an icon next to the existing segment tags:
    * **email**: envelope icon ✉️, color: blue.
    * **sms**: speech bubble icon 💬, color: green.
    * **push**: bell icon 🔔, color: orange.
2.  **SMS Format Preview**: When `primary_channel === "sms"`, add a mobile-style message bubble visual block below the CTA (Call to Action; llamada a la acción). This block should display the first 160 characters of `copy.subject` + " — " + `copy.body_paragraphs[0]`. This demonstrates that the system adapts the format to the channel, not just the content.
3.  **Rationale Display**: Show `channel.reason` as a tooltip (información emergente al pasar el cursor) or small text below the badge to allow explaining the selection logic (the "WHY") during the demo.

## Implementation Constraints
* Keep all existing fallbacks (mecanismos de reserva ante fallos) intact.
* Do not modify `channel_selector.py`, `gemini_client.py`, or any files in the `autonomous/` directory, except for line 338 of `campaign_generator.py`.