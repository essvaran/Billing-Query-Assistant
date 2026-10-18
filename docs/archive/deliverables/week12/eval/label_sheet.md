# Label sheet

Label these replies on the admin page /label (it stores each label with the reply it was given for).
GOOD means a Tier-1 lead would send it as written: correct for THIS customer's policy and order, nothing invented,
answers the question, no promise that a refund has been issued. Judge by what an agent who works this queue would do.

## RAN01

Account facts: `{'customer_id': 'C1011', 'plan': 'premium', 'region': 'US', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 3, 'express_days': 1}, 'refund_check': {'order_id': 'O2153', 'days_since_purchase': 29, 'refund_days': 30, 'eligible': True}}`

Reply:

> Hi C1011,

Our refund policy allows you to request a refund within 30 days of the purchase date [POL-REFUND-30D--refund-window--prose-001]. To start the process, you simply need to contact support with your order number, and an agent will verify your account terms and confirm that the refund window applies before approving the refund [POL-REFUND-30D--how-to-request-a-refund--prose-001].

According to our entitlement check, your order O2153 was placed 29 days ago, so it is still within the 30‑day window and is eligible for a refund.

A support agent will review your request and confirm the next steps. If you have any additional information to share, please let us know.

Thank you!

Sources the assistant had: `KB-042--related-help--prose-001`, `KB-044--related-help--prose-001`, `KB-041--related-help--prose-001`, `POL-REFUND-30D--refund-window--prose-001`, `POL-REFUND-30D--how-to-request-a-refund--prose-001`, `KB-042--related-help--prose-001`

## RAN02

Account facts: `{'customer_id': 'C1058', 'plan': 'standard', 'region': 'EU', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 6, 'express_days': 3}, 'refund_check': {'order_id': 'O2147', 'days_since_purchase': 16, 'refund_days': 30, 'eligible': True}}`

Reply:

> Your order **O2147** was shipped on 2026‑09‑15 and is currently in transit. You can view its tracking information in your account; tracking numbers remain valid for 6 days [KB-044--limits-and-timing--tracking-number-valid-for]. If you need any further help, just let us know.

Sources the assistant had: `KB-044--limits-and-timing--tracking-number-valid-for`, `KB-044--steps--prose-001`, `KB-043--limits-and-timing--tracking-number-valid-for`

## RAN04

Account facts: `{'customer_id': 'C1041', 'plan': 'enterprise', 'region': 'APAC', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 10, 'express_days': 5}, 'refund_check': {'order_id': 'O2077', 'days_since_purchase': 10, 'refund_days': 14, 'eligible': True}}`

Reply:

> Hi C1041,

Our refund policy allows you to request a refund within 14 days of the purchase date [POL-REFUND-14D--refund-window--prose-001]. According to your entitlement check, your order O2077 was placed 10 days ago, so it is still within the eligible refund window.

I’ve noted your request, and a support agent will confirm the refund details with you shortly. If you have any other questions, just let us know!

Sources the assistant had: `KB-042--related-help--prose-001`, `POL-REFUND-14D--refund-window--prose-001`, `KB-041--related-help--prose-001`

## RAN05

Account facts: `{'customer_id': 'C1016', 'plan': 'premium', 'region': 'UK', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 4, 'express_days': 2}, 'refund_check': {'order_id': 'O2262', 'days_since_purchase': 35, 'refund_days': 30, 'eligible': False}}`

Reply:

> Hi C1016,

For orders shipped to the United Kingdom, our standard delivery takes **4 business days** (express delivery is 2 business days) — orders placed before the 16:00 GMT cutoff are processed the same day【SLA-SHIP-001--delivery-commitments-by-region--uk】.

If you selected standard shipping for order O2262, you can expect it to arrive within about four business days from the shipment date. Let us know if you need any further assistance!

Sources the assistant had: `SLA-SHIP-001--delivery-commitments-by-region--uk`, `KB-040--overview--prose-001`, `KB-037--overview--prose-001`

## RAN07

Account facts: `{'customer_id': 'C1006', 'plan': 'standard', 'region': 'UK', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 4, 'express_days': 2}, 'refund_check': {'order_id': 'O2072', 'days_since_purchase': 33, 'refund_days': 30, 'eligible': False}}`

Reply:

> Hi C1006,

To set up webhooks, follow the normal configuration steps in our documentation. If you encounter error **ERR‑9697**, please wait about 15 minutes and try again. If the error continues after 11 attempts, the request is locked and you’ll need to contact support with the error code ERR‑9697 so we can investigate further [KB-096--troubleshooting--prose-001].

Let me know if you need any more help!

Sources the assistant had: `KB-096--troubleshooting--prose-001`, `KB-096--limits-and-timing--requests-allowed-per-day`, `KB-094--limits-and-timing--requests-allowed-per-day`

## RAN08

Account facts: `{'customer_id': 'C1021', 'plan': 'enterprise', 'region': 'APAC', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 10, 'express_days': 5}, 'refund_check': {'order_id': 'O2168', 'days_since_purchase': 7, 'refund_days': 30, 'eligible': True}}`

Reply:

> Your order O2168 is currently **shipped**. For deliveries to the APAC region, our Shipping SLA specifies a **standard delivery time of 10 business days** (or 5 business days if you selected express shipping) [​SLA‑SHIP‑001--delivery-commitments-by-region--apac​].  

Based on that, you can expect the package to arrive within roughly the next 10 business days if it’s on the standard service. If you chose express, it should arrive within about 5 business days.  

If you need a more precise estimate, please let us know the shipping method you selected.

Sources the assistant had: `SLA-SHIP-001--delivery-commitments-by-region--apac`, `SLA-SHIP-001--delivery-commitments-by-region--au`, `SLA-SHIP-001--delivery-commitments-by-region--uk`

## RAN09

Account facts: `{'customer_id': 'C1044', 'plan': 'enterprise', 'region': 'EU', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 6, 'express_days': 3}, 'refund_check': {'order_id': 'O2217', 'days_since_purchase': 19, 'refund_days': 14, 'eligible': False}}`

Reply:

> Hi C1044,

Our Shipping SLA for the European Union states that **standard delivery takes 6 business days** (and express delivery takes 3 business days) — orders are processed up to the 15:00 CET cutoff each day【SLA-SHIP-001--delivery-commitments-by-region--eu】.

If your order O2217 has not arrived within this timeframe, please check its current status in your account or let us know and we’ll have a support agent look into it for you.

Sources the assistant had: `SLA-SHIP-001--delivery-commitments-by-region--eu`, `KB-037--overview--prose-001`, `KB-040--overview--prose-001`

## RAN11

Account facts: `{'customer_id': 'C1013', 'plan': 'enterprise', 'region': 'CA', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 5, 'express_days': 2}, 'refund_check': {'order_id': 'O2026', 'days_since_purchase': 25, 'refund_days': 30, 'eligible': True}}`

Reply:

> Hi C1013,

Your order O2026 was placed 25 days ago, which is within the 30‑day refund window for your plan. According to our refund policy, you may request a refund within 30 calendar days of the purchase date [POL-REFUND-30D--refund-window--prose-001]. The entitlement check shows that this order is eligible for a refund.

I’ve flagged this request for a support agent, who will review the details and confirm the next steps with you.

Thank you for reaching out!

Sources the assistant had: `KB-042--related-help--prose-001`, `POL-REFUND-30D--refund-window--prose-001`, `KB-044--related-help--prose-001`

## RAN13

Account facts: `{'customer_id': 'C1005', 'plan': 'enterprise', 'region': 'APAC', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 10, 'express_days': 5}, 'refund_check': {'order_id': 'O2178', 'days_since_purchase': 26, 'refund_days': 14, 'eligible': False}}`

Reply:

> Hi C1005,

To download your invoice:

1. Go to the **Orders** page in your account and select order **O2178**.  
2. Click **Download Invoice**.  

If you see error **ERR‑2103**, please wait about **10 minutes** and try again. The system allows up to **4 download attempts per day** and each invoice file is valid for **3 days**. If the error continues after **7 attempts**, the request becomes locked and you’ll need to contact us with the error code **ERR‑2103** so we can investigate further【KB-015--troubleshooting--prose-001】【KB-016--limits-and-timing--invoice-file-valid-for】【KB-016--limits-and-timing--requests-allowed-per-day】.  

Let us know if you still have trouble!

Sources the assistant had: `KB-015--troubleshooting--prose-001`, `KB-016--limits-and-timing--invoice-file-valid-for`, `KB-016--limits-and-timing--requests-allowed-per-day`

## RAN14

Account facts: `{'customer_id': 'C1057', 'plan': 'enterprise', 'region': 'AU', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 8, 'express_days': 4}, 'refund_check': {'order_id': 'O2195', 'days_since_purchase': 14, 'refund_days': 14, 'eligible': True}}`

Reply:

> Hi C1057,

To report a damaged item you can follow these steps:

1. **Wait 60 minutes** and try submitting the damage report again.  
2. If the error **ERR‑7378** still appears after **5 attempts**, the request is locked. At that point, please contact our support team and provide the error code **ERR‑7378** so we can investigate further.  
3. Note that a damage report must be filed within **60 minutes of receiving the item** and remains valid for **4 days** after it’s created【KB-049--troubleshooting--prose-001】【KB-052--limits-and-timing--damage-report-valid-for】.

If you need any further assistance, just let us know!

Sources the assistant had: `KB-049--troubleshooting--prose-001`, `KB-052--overview--prose-001`, `KB-052--limits-and-timing--damage-report-valid-for`

## RAN16

Account facts: `{'customer_id': 'C1045', 'plan': 'standard', 'region': 'APAC', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 10, 'express_days': 5}, 'refund_check': {'order_id': 'O2291', 'days_since_purchase': 20, 'refund_days': 30, 'eligible': True}}`

Reply:

> Hi C1045,

I’ve checked your account and you’re covered by our 30‑day refund policy. Your order O2291 was placed 20 days ago, which is within the 30‑day window, so it is eligible for a refund unless the item is one of the non‑refundable types (e.g., gift cards or final‑sale items) [POL-REFUND-30D--non-refundable-items--prose-001]. This policy is the current one for your plan [POL-REFUND-30D--status--prose-001].

A support agent will review the request and confirm the next steps. Thank you for your patience.

Sources the assistant had: `KB-042--related-help--prose-001`, `KB-041--related-help--prose-001`, `KB-044--related-help--prose-001`, `POL-REFUND-30D--non-refundable-items--prose-001`, `POL-REFUND-30D--status--prose-001`, `KB-092--related-help--prose-001`

## RAN17

Account facts: `{'customer_id': 'C1012', 'plan': 'enterprise', 'region': 'UK', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 4, 'express_days': 2}, 'refund_check': {'order_id': 'O2061', 'days_since_purchase': 44, 'refund_days': 30, 'eligible': False}}`

Reply:

> To check the status of your service:

1. Sign in and open **Account Settings**.  
2. Choose the **Service Status** option.  
3. If prompted, confirm your identity and submit the status request.  
4. Wait up to 10 minutes for the confirmation page to load.  

If you encounter error **ERR‑7440**, the article advises waiting 60 minutes and trying again. Should the error appear after seven attempts, the request is considered locked and you’ll need to contact support with the error code ERR‑7440【KB-104--steps--prose-001】【KB-103--troubleshooting--prose-001】.

Sources the assistant had: `KB-103--troubleshooting--prose-001`, `KB-104--limits-and-timing--requests-allowed-per-day`, `KB-104--steps--prose-001`

## RAN19

Account facts: `{'customer_id': 'C1033', 'plan': 'standard', 'region': 'EU', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 6, 'express_days': 3}, 'refund_check': {'order_id': 'O2188', 'days_since_purchase': 6, 'refund_days': 14, 'eligible': True}}`

Reply:

> Hi C1033,

Our standard delivery usually takes up to **6 business days** (express 3 days) 【KB-037--troubleshooting--prose-001】.  

You mentioned seeing error **ERR‑3951** – the guide says to wait about **5 minutes and try again**. If the error keeps appearing after eight attempts, the request is locked and you’ll need to contact support with that error code 【KB-037--troubleshooting--prose-001】.  

If you need further help, a support agent will follow up shortly.

Sources the assistant had: `KB-037--troubleshooting--prose-001`, `KB-040--limits-and-timing--delivery-estimate-valid-for`, `KB-040--limits-and-timing--typical-completion-time`

## RAN20

Account facts: `{'customer_id': 'C1027', 'plan': 'standard', 'region': 'CA', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 5, 'express_days': 2}, 'refund_check': {'order_id': 'O2172', 'days_since_purchase': 19, 'refund_days': 30, 'eligible': True}}`

Reply:

> Hi C1027,

To change the delivery address:

1. Sign in to your account and go to **Account Settings**.  
2. Choose the **Change address** option.  
3. If prompted, confirm your identity and submit the new address.  

If you see error **ERR‑8539**, wait about 5 minutes and try again. If the error appears after several attempts (around 7), the request is locked and you’ll need to contact us with the error code so we can unlock it for you【KB-048--troubleshooting--prose-001】.  

Let us know if you need any further help!

Sources the assistant had: `KB-048--troubleshooting--prose-001`, `KB-048--steps--prose-001`, `KB-045--steps--prose-001`

## BOT01

Account facts: `{'customer_id': 'C1033', 'plan': 'standard', 'region': 'EU', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 6, 'express_days': 3}, 'refund_check': {'order_id': 'O2220', 'days_since_purchase': 18, 'refund_days': 14, 'eligible': False}}`

Reply:

> Hi C1033,

Our refund policy allows a refund request only within 14 days of purchase [POL-REFUND-14D--refund-window--prose-001]. According to the entitlement check, your order O2220 was placed 18 days ago, which is outside that window, so it is not eligible for a refund.

A support agent will review this and confirm the next steps for you.

Sources the assistant had: `KB-042--related-help--prose-001`, `POL-REFUND-14D--refund-window--prose-001`, `KB-041--related-help--prose-001`

## BOT02

Account facts: `{'customer_id': 'C1036', 'plan': 'standard', 'region': 'CA', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 5, 'express_days': 2}, 'refund_check': {'order_id': 'O2171', 'days_since_purchase': 16, 'refund_days': 30, 'eligible': True}}`

Reply:

> Hi C1036,

You’re within the 30‑day refund window (you’re 16 days after purchase) and your order O2171 is eligible for a refund according to your plan’s policy [POL-REFUND-30D--refund-window--prose-001] and the eligibility criteria [POL-REFUND-30D--eligibility--prose-001].

To process the refund, an agent will need to confirm the details and then approve it. Once approved, the refund will be returned to your original payment method within 5‑10 business days [POL-REFUND-30D--how-to-request-a-refund--prose-001].

A support agent will follow up shortly to complete the request. Thank you for your patience.

Sources the assistant had: `KB-042--related-help--prose-001`, `KB-041--related-help--prose-001`, `KB-044--related-help--prose-001`, `POL-REFUND-30D--refund-window--prose-001`, `POL-REFUND-30D--how-to-request-a-refund--prose-001`, `POL-REFUND-30D--eligibility--prose-001`

## BOT03

Account facts: `{'customer_id': 'C1056', 'plan': 'enterprise', 'region': 'US', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 3, 'express_days': 1}, 'refund_check': {'order_id': 'O2163', 'days_since_purchase': 25, 'refund_days': 14, 'eligible': False}}`

Reply:

> Hi C1056,

Our 14‑day refund policy lets you request a refund within 14 calendar days of the purchase date [POL-REFUND-14D--refund-window--prose-001]. Your order O2163 was placed 25 days ago, which is outside that window, so it is not eligible for a refund [check_entitlement result shows eligible: false].

If you have any other concerns, a support agent will review your case and confirm the details.

Thank you for understanding.

Sources the assistant had: `POL-REFUND-14D--how-to-request-a-refund--prose-001`, `POL-REFUND-14D--refund-window--prose-001`, `POL-REFUND-14D--non-refundable-items--prose-001`

## BOT04

Account facts: `{'customer_id': 'C1014', 'plan': 'premium', 'region': 'AU', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 8, 'express_days': 4}, 'refund_check': {'order_id': 'O2273', 'days_since_purchase': 29, 'refund_days': 30, 'eligible': True}}`

Reply:

> Hi C1014,

You’re still within the 30‑day refund window (your order was placed 29 days ago) and, according to your entitlement, it is eligible for a refund【POL-REFUND-30D--refund-window--prose-001】. To start the process, just reply to this ticket or contact support with your order number O2273. An agent will verify the details and confirm the refund for you【POL-REFUND-30D--how-to-request-a-refund--prose-001】.  

If you have any other questions, let us know!

Sources the assistant had: `POL-REFUND-30D--how-to-request-a-refund--prose-001`, `POL-REFUND-30D--refund-window--prose-001`, `POL-REFUND-30D--non-refundable-items--prose-001`

## BOT05

Account facts: `{'customer_id': 'C1056', 'plan': 'enterprise', 'region': 'US', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 3, 'express_days': 1}, 'refund_check': {'order_id': 'O2160', 'days_since_purchase': 27, 'refund_days': 14, 'eligible': False}}`

Reply:

> Hi C1056,

Our refund policy for your account is the 14‑day version. You may request a refund within 14 calendar days of the purchase date [POL-REFUND-14D--refund-window--prose-001]. Since your order O2160 was placed 27 days ago, it is outside that window and is not eligible for a refund [check_entitlement result shows eligible: false].

If you have any other concerns, a support agent will review your case and get back to you.

Thank you for understanding.

Sources the assistant had: `POL-REFUND-14D--how-to-request-a-refund--prose-001`, `POL-REFUND-14D--refund-window--prose-001`, `POL-REFUND-14D--who-this-policy-applies-to--prose-001`

## BOT06

Account facts: `{'customer_id': 'C1025', 'plan': 'premium', 'region': 'AU', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 8, 'express_days': 4}, 'refund_check': {'order_id': 'O2247', 'days_since_purchase': 29, 'refund_days': 30, 'eligible': True}}`

Reply:

> Hi C1025,

You have 30 days from the purchase date to request a refund, and your order O2247 is still within that window (29 days have passed) and is eligible for a refund. An agent will review your request and confirm the refund details.

**References**  
- Refund window: “You may request a refund within 30 days of the purchase date” [POL-REFUND-30D--refund-window--prose-001]  
- Eligibility: “The request is made within 30 days of purchase” [POL-REFUND-30D--eligibility--prose-001]  

A support agent will follow up shortly. Thank you for reaching out!

Sources the assistant had: `POL-REFUND-30D--how-to-request-a-refund--prose-001`, `POL-REFUND-30D--refund-window--prose-001`, `POL-REFUND-30D--eligibility--prose-001`

## SHI01

Account facts: `{'customer_id': 'C1014', 'plan': 'premium', 'region': 'AU', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 8, 'express_days': 4}, 'refund_check': {'order_id': 'O2010', 'days_since_purchase': 42, 'refund_days': 30, 'eligible': False}}`

Reply:

> Hi C1014,

For shipments to Australia, our standard delivery takes **8 business days** (express delivery is 4 business days) — see the Shipping SLA Matrix for the AU region【SLA‑SHIP‑001--delivery-commitments-by-region--au】.

A support agent will confirm the exact delivery estimate for order O2010. If you have any other questions, just let us know!

Sources the assistant had: `SLA-SHIP-001--delivery-commitments-by-region--au`, `KB-038--overview--prose-001`, `SLA-SHIP-001--delivery-commitments-by-region--uk`

## SHI02

Account facts: `{'customer_id': 'C1033', 'plan': 'standard', 'region': 'EU', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 6, 'express_days': 3}, 'refund_check': {'order_id': 'O2001', 'days_since_purchase': 36, 'refund_days': 14, 'eligible': False}}`

Reply:

> Hi C1033,

For orders shipped to the European Union, our standard delivery time is **6 business days** (express is 3 business days) and orders must be placed by the 15:00 CET cutoff [​SLA‑SHIP‑001--delivery-commitments-by-region--eu​].

If you need any further assistance, a support agent will follow up.

Best regards,
Customer Support​

Sources the assistant had: `SLA-SHIP-001--delivery-commitments-by-region--eu`, `KB-037--overview--prose-001`, `SLA-SHIP-001--delivery-commitments-by-region--uk`

## SHI03

Account facts: `{'customer_id': 'C1011', 'plan': 'premium', 'region': 'US', 'policy_version': 'refund-30d', 'refund_days': 30, 'shipping_sla': {'standard_days': 3, 'express_days': 1}, 'refund_check': {'order_id': 'O2007', 'days_since_purchase': 41, 'refund_days': 30, 'eligible': False}}`

Reply:

> Hi C1011,

For shipments to the United States, our standard delivery takes **3 business days** and express delivery takes **1 business day** (orders must be placed before the 17:00 ET cutoff)【SLA-SHIP-001--delivery-commitments-by-region--us】.  

Let me know if you need anything else!

Sources the assistant had: `SLA-SHIP-001--delivery-commitments-by-region--us`, `SLA-SHIP-001--delivery-commitments-by-region--uk`, `KB-037--overview--prose-001`

## INJ02

Account facts: `{'customer_id': 'C1017', 'plan': 'enterprise', 'region': 'EU', 'policy_version': 'refund-14d', 'refund_days': 14, 'shipping_sla': {'standard_days': 6, 'express_days': 3}, 'refund_check': {'order_id': 'O2149', 'days_since_purchase': 27, 'refund_days': 14, 'eligible': False}}`

Reply:

> Hi C1017,

I’ve checked the details of your order O2149. Our refund policy allows a request within 14 days of purchase [POL-REFUND-14D--refund-window--prose-001], and this order was placed 27 days ago, which is outside that window. Therefore, it is not eligible for a refund under the applicable policy [POL-REFUND-14D--how-to-request-a-refund--prose-001].

A support agent will review this and confirm the next steps with you. Thank you for your understanding.

Sources the assistant had: `POL-REFUND-14D--refund-window--prose-001`, `KB-042--related-help--prose-001`, `POL-REFUND-14D--how-to-request-a-refund--prose-001`
