# Session preamble (one-off chat)

Send this as the first message in a one-off ChatGPT session, together with the uploaded context files and run artifacts. Everything a one-off session needs is already in context once uploaded, so this stays thin — it does not restate detail already reliably available in the uploaded files.

---

Before answering anything substantive, read the attached `ingestion-contract.md` and `query-policy.md` in full. Follow their rules for schema handling, sidecar joins and asymmetry, identity merging, evidence order, confidence labels, authority boundaries, and the query policy's pre-response check for each later substantive request.

Run the initial ingestion validation described in `ingestion-contract.md` and reply with only that validation summary — files recognized, workspaces/regions, sidecar pairing status, and obvious gaps. Do not produce a newsletter, leadership report, event digest, or other substantive analysis until asked.

If `f3-domain-context.md`, an augmentation index, or a named dated augmentation is attached, note that it was recognized, but treat cultural context as background and augmentations as conditional evidence per the query policy — not as proof of a current fact on its own.
