import json
import db
from response import created, bad_request
from fields import InteractionField, InteractionType, LambdaEvent, LambdaResponse, HttpMethod

_INSERT_SQL = """
    INSERT INTO interactions (user_id, event_id, type) VALUES (%s, %s, %s)
    RETURNING interaction_id, created_at
"""


def handler(event, context):
    if event[LambdaEvent.HTTP_METHOD] != HttpMethod.POST:
        return {LambdaResponse.STATUS_CODE: 405, LambdaResponse.BODY: json.dumps({"error": "Method not allowed"})}

    body = json.loads(event.get(LambdaEvent.BODY) or "{}")
    event_id = body.get(InteractionField.EVENT_ID)
    interaction_type = body.get(InteractionField.TYPE)

    if not event_id:
        return bad_request("event_id is required")
    if interaction_type not in list(InteractionType):
        return bad_request(f"type must be one of: {', '.join(sorted(InteractionType))}")

    user_id = event[LambdaEvent.REQUEST_CONTEXT][LambdaEvent.AUTHORIZER][LambdaEvent.CLAIMS][LambdaEvent.SUB]
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_INSERT_SQL, (user_id, event_id, interaction_type))
        row = dict(cur.fetchone())
        conn.commit()

    return created({
        InteractionField.ID: str(row[InteractionField.ID]),
        InteractionField.CREATED_AT: str(row[InteractionField.CREATED_AT]),
    })
