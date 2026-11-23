# MODICS — Shop Order Interface for Press PRS 63

**Interface contract — ERP (IFS) → press terminal**
Version 1.1 · October 2026 · Owner: Industrialisation / IoT, Bulgin TN

## 1. Purpose

The Raspberry Pi terminal of injection press **PRS 63** exposes a small HTTP/JSON API.
The ERP (or the middleware acting on its behalf) **pushes the list of shop orders waiting
for this machine**. The terminal shows them to the operator, who selects the next one to run
and confirms it on screen. The ERP can also read the current production status.

The ERP side is the **client**; the press terminal is the **server**. Nothing has to be
installed on the ERP server beyond the ability to send HTTP requests.

## 2. Connection

| Item | Value |
|---|---|
| Base URL | `http://192.168.81.56:8080/api/v1` (IP and port provided separately) |
| Authentication | HTTP header `X-Api-Key: <key>` on every call except `/health` |
| Content type | `application/json; charset=utf-8`, request body ≤ 64 KB |
| Network | Reachable only from the production VLAN / ERP server IP (firewall rule). Plain HTTP; a TLS reverse-proxy can be put in front if the flow must leave the trusted network. |
| Machine check | Every POST may carry `"machine": "PRS 63"`; a different value is rejected (`400`) — protects against mis-routing to the wrong press. |

## 3. Endpoints

### 3.1 `POST /shop-orders` — synchronise the queue (recommended)

Replaces the complete list of **pending** shop orders for the machine. Idempotent: send the
full current list each time something changes in IFS (new order, cancellation, re-sequencing).
The order currently **in production** is never affected.

**Request**
```json
{
  "machine": "PRS 63",
  "orders": [
    {
      "shop_order":   "X15241/2",
      "part_number":  "PX0588",
      "tool_number":  "T-2222",
      "cycle_time":   25.0,
      "cavities":     4,
      "material_ref": "Z2201/028",
      "quantity":     20000,
      "sequence":     1,
      "due_date":     "2026-10-06"
    },
    { "shop_order": "X15277/1", "part_number": "PX0412", "tool_number": "T-1087",
      "cycle_time": 32.5, "cavities": 2, "material_ref": "Z2201/030",
      "quantity": 5000, "sequence": 2 }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `shop_order` | string | yes | IFS shop order number — unique key in the queue |
| `part_number` | string | yes | Part number |
| `tool_number` | string | yes | Tool / mould number |
| `cycle_time` | number | yes, > 0 | Theoretical cycle time, **seconds** |
| `cavities` | integer | yes, > 0 | Active cavities |
| `material_ref` | string | yes | Material reference |
| `quantity` | integer | yes, > 0 | Quantity to produce (pieces) |
| `sequence` | integer | no | Display / priority order (1 = first). Default: end of list |
| `due_date` | string | no | Free text shown to the operator, e.g. `2026-10-06` |

**Responses**

| Code | Body | Meaning |
|---|---|---|
| `202` | `{"accepted":2,"rejected":[],"action":"queued","queue":["X15241/2","X15277/1"]}` | All orders accepted. `action` = `queued` (press busy, list shown at end of production) or `offered` (press free, list shown to the operator now) |
| `207` | `{"accepted":1,"rejected":[{"index":1,"shop_order":"X15299/1","error":"Missing field: part_number"}], …}` | Partial: valid orders stored, invalid ones listed with the reason |
| `400` | `{"error":"Wrong machine: PRS 67 (this terminal is PRS 63)"}` | Payload rejected as a whole |
| `401` | `{"error":"unauthorized"}` | Missing / wrong API key |
| `413` | `{"error":"body too large"}` | Body > 64 KB |

### 3.2 `POST /shop-order` — add or update one order

Same fields as one element of `orders` above (optional `"machine"`). Inserts the order in the
queue or updates it if `shop_order` already exists.

Optional `"auto_apply": true` starts the order **immediately without operator confirmation**
if the press is free. Default `false` (operator confirms on screen). To be agreed before use.

Response `202`: `{"accepted":true,"action":"queued|offered|applied","shop_order":"X15241/2"}`

### 3.3 `DELETE /shop-orders/{shop_order}` — remove one order

URL-encode the identifier (`X15241/2` → `X15241%2F2`).
`200 {"shop_order":"X15241/2","removed":true}` or `404` if not in the queue.

### 3.4 `GET /queue` — read the pending list

```json
{ "machine": "PRS 63",
  "orders": [ { "shop_order": "X15241/2", "part_number": "PX0588", "tool_number": "T-2222",
                "cycle_time": 25.0, "cavities": 4, "material_ref": "Z2201/028",
                "quantity": 20000, "sequence": 1, "due_date": "2026-10-06",
                "received_at": "2026-10-02T09:12:03" } ] }
```

### 3.5 `GET /status` — current production status (read-only)

```json
{
  "machine": "PRS 63", "state": "Production", "of_active": true,
  "shop_order": "X15241/2", "part_number": "PX0588", "tool_number": "T-2222",
  "cavities": 4, "cycle_time_target": 25.0, "quantity": 20000,
  "produced": 8468, "good": 8452, "rejects": 16, "remaining": 11532,
  "trs_global": 78.4,
  "queue_length": 2, "next_shop_order": "X15277/1",
  "time": "2026-10-02T09:12:03"
}
```
`state`: `Production`, `Arrêt` (stopped) or `idle` (no order running). Lets the ERP know
whether the press is free before pushing, and follow progress of the running order.

### 3.6 `GET /health` — monitoring (no key)

`{"status":"ok","machine":"PRS 63","time":"…"}`

## 4. Behaviour on the press terminal

| Situation | What happens |
|---|---|
| Press **free**, orders received | The operator sees the pending list, taps an order, checks the pre-filled form, confirms |
| Press **in production**, orders received | Orders are stored; a short notice is shown. At "End of production" the list is displayed automatically |
| Order started by the operator | It is removed from the pending list (the ERP can confirm via `GET /queue`) |
| Order cancelled in IFS | Send the new full list (`POST /shop-orders`) or `DELETE /shop-orders/{id}` — the list on screen is refreshed |
| Terminal restart | The pending list is persisted locally and restored |

The shop order **running** on the press is not changed by the API (safety). To change it, the
operator ends the current production on screen, then selects the next order.

## 5. Quick test

```bash
curl -s http://192.168.81.56:8080/api/v1/health

curl -s -X POST http://192.168.81.56:8080/api/v1/shop-orders \
  -H "X-Api-Key: <key>" -H "Content-Type: application/json" \
  -d '{"machine":"PRS 63","orders":[{"shop_order":"TEST/1","part_number":"PX0588",
       "tool_number":"T-2222","cycle_time":25,"cavities":4,"material_ref":"Z2201/028",
       "quantity":100,"sequence":1}]}'

curl -s -H "X-Api-Key: <key>" http://<press-63-ip>:8080/api/v1/queue
curl -s -X DELETE -H "X-Api-Key: <key>" "http://<press-63-ip>:8080/api/v1/shop-orders/TEST%2F1"
```

## 6. Open points to agree

1. **Trigger on the ERP side**: event-driven on shop order release / change in IFS (preferred),
   or scheduled sync (e.g. every 5 min) — both work with `POST /shop-orders`.
2. **`auto_apply`**: operator confirmation (default) vs. automatic start.
3. **Key exchange**: the API key will be sent through a separate secure channel.
4. **Future presses** (PRS 67): same contract, one base URL per press, `machine` field changes.
