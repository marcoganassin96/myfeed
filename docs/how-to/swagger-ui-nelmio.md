# How to Use the Swagger UI (NelmioApiDocBundle)

Covers: opening the UI locally, trying requests, and keeping docs in sync as code changes.

---

## 1. Start the local stack

```bash
docker-compose up -d
```

MDG runs at `http://localhost:9000`. Swagger UI is available at `/api/doc` — routes are registered in `config/routes/nelmio_api_doc.yaml` and loaded for all environments.

---

## 2. Open Swagger UI

```
http://localhost:9000/api/doc
```

Raw OpenAPI 3 JSON spec (importable into Postman / Insomnia):

```
http://localhost:9000/api/doc.json
```

---

## 3. Authorize requests in the UI

MDG validates `X-User-ID` (injected from a Cognito JWT upstream). In local dev there is no real Cognito, so pass any string directly — it does not need to be a UUID.

1. Click **Authorize** (top right, lock icon)
2. Under **bearerAuth**, enter any string — e.g. `local-dev-token`
3. Click **Authorize** → **Close**

The UI will include `Authorization: Bearer local-dev-token` on every **Try it out** request.

> The `X-User-ID` header is set by `UserContextListener` from the JWT in production. Locally, set it manually per request in the **Try it out** form under **Parameters → X-User-ID**. Any string works: `mock-user-0001`, `test-user`, etc.

---

## 4. Try a request

1. Expand an operation (e.g. `GET /master-data/newsletters`)
2. Click **Try it out**
3. Fill in `X-User-ID` with any string (e.g. `mock-user-0001`)
4. Click **Execute**
5. Inspect **Response body**, **Response headers**, and **Curl** command

---

## 5. Keep docs consistent when code changes

The spec is **code-first** — Nelmio reads your PHP attributes at request time. No build step needed. The contract is:

| Code change | What Nelmio picks up automatically | What you must update manually |
|---|---|---|
| New `#[Route]` on existing controller | Route appears in spec (method + path) | Add `#[OA\Get/Post/...]`, `#[OA\Parameter]`, `#[OA\Response]` |
| Route path or method changes | Path + method update automatically | Update any `#[OA\Parameter(in: 'path')]` whose `name` matches the route placeholder |
| New controller class | Routes appear in spec if under `/master-data` | Add `#[OA\Tag]` to the class to group operations |
| Endpoint deleted | Route disappears automatically | Nothing — OA attributes are gone with the method |
| Response shape changes | Nothing — Nelmio doesn't read return types | Update `#[OA\Response]` content properties to match the new shape |
| Request body field added/removed | Nothing | Update `#[OA\RequestBody]` properties accordingly |

### Checklist for adding a new endpoint

```
[ ] Add #[Route(...)] and the method
[ ] Add #[OA\Get/Post/Put/Patch/Delete(summary: '...')]
[ ] Add #[OA\Parameter] for every path and header param
[ ] Add #[OA\RequestBody] if POST/PUT/PATCH with a body
[ ] Add #[OA\Response] for every status code the method can return
[ ] Reload http://localhost:9000/api/doc and verify the operation appears
```

### Checklist for adding a new controller

```
[ ] Add #[OA\Tag(name: 'ResourceName')] on the class
[ ] Follow the per-endpoint checklist above for each method
[ ] Verify the new tag group appears in the UI
```

---

## 6. Confirm the spec stays valid

Nelmio generates the spec on each request to `/api/doc.json` — there is no separate build artifact to go stale. To catch missing or malformed attributes early:

```bash
# Fetch the spec from the running container and validate it is valid JSON
curl -s http://localhost:9000/api/doc.json | python3 -m json.tool > /dev/null && echo "valid JSON"
```

For deeper validation (checks OpenAPI 3 schema compliance):

```bash
# Install once
npm install -g @stoplight/spectral-cli

# Validate
spectral lint http://localhost:9000/api/doc.json
```

---

## 7. Import into Postman

1. Open Postman → **Import**
2. Select **Link** and enter `http://localhost:9000/api/doc.json`
3. Postman generates a collection from the spec — all operations, params, and body schemas pre-filled
4. Set a `baseUrl` variable to `http://localhost:9000` and `X-User-ID` to any test UUID
