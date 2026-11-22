"""One-time read-only public provider probe (no credentials, no private data).

GitHub Actions runs this only for the public query "Calin".
Prints HTTP status, content type and JSON field types, not raw response
contents. This is diagnostics, not a guarantee of hosting connectivity.
"""
import json
import httpx

TESTS=[
    ("Gigora","https://gigora.live/api/ai/events",{"artist":"Calin","limit":4}),
    ("StungEvents","https://api.stungevents.com/search",{"q":"Calin"}),
    ("Ticket Fairy","https://www.ticketfairy.com/api/v1/events/listing",
        {"search":"Calin","section_type":"upcoming","sort":"start_date","order":"asc","size":4}),
]
for name,url,params in TESTS:
    try:
        with httpx.Client(timeout=8,follow_redirects=False) as client:
            r=client.get(url,params=params,headers={"Accept":"application/json",
                  "User-Agent":"Ceyrl-Public-Provider-Diagnostics/1.0"})
        print(f"PROBE {name}: http={r.status_code} type={r.headers.get('content-type','?').split(';')[0]} bytes={len(r.content)} redirect={bool(r.is_redirect)}")
        if r.status_code==200:
            try:
                data=r.json()
                if isinstance(data,dict):
                    print(f"PROBE {name}: top_level_keys={list(data.keys())[:20]}")
                    for field in ("events","data"):
                        value=data.get(field)
                        if isinstance(value,list):
                            print(f"PROBE {name}: {field}_length={len(value)}")
                            if value and isinstance(value[0],dict):
                                print(f"PROBE {name}: sample_field_names={list(value[0].keys())[:24]}")
                        elif isinstance(value,dict):
                            print(f"PROBE {name}: {field}_keys={list(value.keys())[:15]}")
                            nested=value.get("events")
                            if isinstance(nested,list):
                                print(f"PROBE {name}: nested_events_length={len(nested)}")
                else:
                    print(f"PROBE {name}: json_is_{type(data).__name__}")
            except ValueError:
                print(f"PROBE {name}: non_json_body")
    except httpx.HTTPError as exc:
        print(f"PROBE {name}: network_error={type(exc).__name__}")
