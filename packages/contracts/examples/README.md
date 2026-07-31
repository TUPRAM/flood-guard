# Contract examples

The GeoAI v2 examples are synthetic, redacted, non-operational contract
fixtures. They do not contain a trained production model, qualified Thailand
reference labels, agency acceptance, or evidence that may feed the decision
layer.

`model-registry-entry-v1.candidate.json` is intentionally signed so tests can
verify the complete example chain. Its HMAC key is public test material:

```text
key_id: synthetic-registry-authority
key_utf8: floodguard-contract-fixture-signing-key-v1
```

Never configure this key in a deployed registry authority. Manifest and payload
digests use deterministic JSON serialization with UTF-8, sorted object keys, no
ASCII escaping, no non-finite numbers, and separators `,` and `:` without
whitespace. Formatting whitespace in the checked-in JSON files is therefore not
part of the digest; every parsed field and value is.
