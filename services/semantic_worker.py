import argparse
import json


def _normalize_rows(arr):

    x = np.array(arr, dtype="float32")
    if x.ndim == 1:
        x = x.reshape(1, -1)
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return x / norms


def cmd_warmup(model: str):
    from sentence_transformers import SentenceTransformer

    m = SentenceTransformer(model)
    _ = m.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False)
    print(json.dumps({"ok": True}, ensure_ascii=False))


def cmd_embed(payload: str):
    from sentence_transformers import SentenceTransformer

    data = json.loads(payload)
    model = data["model"]
    texts = data.get("texts", [])
    m = SentenceTransformer(model)
    vecs = m.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    print(json.dumps({"vectors": vecs.tolist()}, ensure_ascii=False))


def cmd_rank(payload: str):
    import faiss

    data = json.loads(payload)
    q = _normalize_rows(data["query"])
    vs = _normalize_rows(data.get("vectors", []))
    limit = int(data.get("limit", 50))

    if vs.shape[0] == 0:
        print(json.dumps({"results": []}, ensure_ascii=False))
        return

    index = faiss.IndexFlatIP(vs.shape[1])
    index.add(vs.astype("float32"))
    scores, ids = index.search(q.astype("float32"), min(limit, vs.shape[0]))

    out = []
    for i, s in zip(ids[0], scores[0]):
        if int(i) < 0:
            continue
        out.append([int(i), float(s)])

    print(json.dumps({"results": out}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_w = sub.add_parser("warmup")
    p_w.add_argument("--model", required=True)

    p_e = sub.add_parser("embed")
    p_e.add_argument("--payload", required=True)

    p_r = sub.add_parser("rank")
    p_r.add_argument("--payload", required=True)

    args = parser.parse_args()
    if args.cmd == "warmup":
        cmd_warmup(args.model)
    elif args.cmd == "embed":
        cmd_embed(args.payload)
    elif args.cmd == "rank":
        cmd_rank(args.payload)


if __name__ == "__main__":
    main()
