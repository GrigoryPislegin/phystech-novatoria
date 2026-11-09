def similarity_between(src_norm: str, dst_norm: str) -> float:
    """Similarity of two normalized strings (0-1). Exact match or one contains the other."""
    if not dst_norm:
        return 0.0
    src_l = src_norm.lower().strip()
    dst_l = dst_norm.lower().strip()
    if src_l == dst_l:
        return 1.0
    if src_l in dst_l or dst_l in src_l:
        return 0.8
    return 0.0
