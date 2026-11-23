"""CV · Computer vision: passenger counts and mobility aids (pretrained detectors → anonymized counts)

Generated from the notebook (cells 14) by tools/build_from_notebook.py. Do not edit by hand: edit the notebook
and rebuild. Modules run in ONE shared namespace, in the order in transit_ai/_modules.json, like the notebook.
"""
# ruff: noqa

# ----------------------------------------------------------------------------------------------------
# CV · Computer vision: passenger counts and mobility aids (pretrained detectors → anonymized counts)   [notebook cell 14]
# ----------------------------------------------------------------------------------------------------
USE_CV = param("USE_CV", False)  # notebook form field; override with an environment variable
CV_SCORE_THRESHOLD = param("CV_SCORE_THRESHOLD", 0.75)  # notebook form field; override with an environment variable
CV_VIDEO_FRAMES = param("CV_VIDEO_FRAMES", 8)  # notebook form field; override with an environment variable
SHOW_CV_PREVIEW = param("SHOW_CV_PREVIEW", False)  # notebook form field; override with an environment variable
# Mobility aids (accessibility needs): wheelchairs, walkers and crutches are counted, never people's traits.
# The detector looks for OBJECTS; it never estimates age, disability, race or gender from anyone's appearance.
USE_MOBILITY_AID_CV = param("USE_MOBILITY_AID_CV", False)  # notebook form field; override with an environment variable
MOBILITY_SCORE_THRESHOLD = param("MOBILITY_SCORE_THRESHOLD", 0.15)  # notebook form field; override with an environment variable
MOBILITY_MODEL_ID = "google/owlvit-base-patch32"   # open-vocabulary detector: finds objects named in text prompts
# Each class is searched with a few text prompts; strollers are reported (caregivers need room to board) but not scored.
MOBILITY_PROMPTS = {"wheelchair": ["a wheelchair", "a person in a wheelchair"],
                    "walker": ["a walker", "a rollator walking frame"],
                    "crutches": ["crutches"],
                    "stroller": ["a baby stroller"]}
MOBILITY_AID_CLASSES = ("wheelchair", "walker", "crutches")
# Labelled wheelchair images (Apache-2.0): a stand-in for an accessible stop camera, and V6's mobility-aid test set
MOBILITY_DATASET = "Falah/wheel-chair-images-annotation4object-detec"
MOBILITY_DATASET_LABELS = {0: "person", 1: "wheelchair", 2: "not wheelchair"}
import numpy as np

# Sample transit imagery, downloaded at runtime. Only person counts leave this cell; images are not saved.
#  - bus.jpg: riders at the curb beside a city bus (Ultralytics sample asset, AGPL-3.0)
#  - vtest.avi: overhead camera of pedestrians on a walkway (OpenCV sample data), used as a station-approach camera
CV_SOURCES = [
    {"camera_id": "VISION-STOP-NEWARK-PENN", "kind": "image", "role": "bus stop curb camera",
     "url": "https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/assets/bus.jpg",
     "stop_id": "NEWARK_PENN_BUS_LANE", "capacity": 50,
     "note": "generic street photo used as a stand-in for a Newark Penn curb camera"},
    {"camera_id": "VISION-APPROACH-NEWARK-PENN", "kind": "video", "role": "station approach camera",
     "url": "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/vtest.avi",
     "stop_id": "NEWARK_PENN_APPROACH", "capacity": 50,
     "note": "public pedestrian video used as a stand-in for a station approach camera"},
    {"camera_id": "VISION-STOP-HOSPITAL-ACCESS", "kind": "dataset", "role": "accessible stop camera",
     "url": f"hf://datasets/{MOBILITY_DATASET}", "stop_id": "R2_HOSPITAL_STOP", "capacity": 50, "pick": "visible_wheelchair",
     "note": "labelled wheelchair photo (Hugging Face, Apache-2.0) used as a stand-in for an accessible stop camera; "
             "chosen as the first labelled image in a fixed order where the detector finds the wheelchair, so it shows "
             "what a detection looks like (it is left out of V6's accuracy test)"},
]
CV_DIR = os.path.join(OUTPUT_DIR, "cv_cache")      # downloaded samples only; nothing derived from them is written here
os.makedirs(CV_DIR, exist_ok=True)
_DETECTOR = {"name": None, "model": None, "error": []}
_MOBILITY = {"name": None, "model": None, "error": []}
_MOBILITY_DATA = {"df": None, "error": None, "demo": None}
MOBILITY_DEMO_TRIES = 40   # labelled wheelchair images tried, in a fixed shuffled order, for the accessible stop camera


def load_detector():
    """Faster R-CNN (MobileNetV3, COCO) from torchvision; OpenCV's HOG people detector if torchvision weights fail."""
    if _DETECTOR["name"]:
        return _DETECTOR["name"]
    try:
        import torch, torchvision
        from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_fpn, FasterRCNN_MobileNet_V3_Large_FPN_Weights
        w = FasterRCNN_MobileNet_V3_Large_FPN_Weights.DEFAULT
        m = fasterrcnn_mobilenet_v3_large_fpn(weights=w).eval()
        _DETECTOR.update(name=f"torchvision Faster R-CNN MobileNetV3 ({w.name}, COCO)", model=("torch", m, w))
        return _DETECTOR["name"]
    except Exception as e:
        _DETECTOR["error"].append(f"torchvision: {type(e).__name__}: {str(e)[:120]}")
    try:
        import cv2
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        _DETECTOR.update(name="OpenCV HOG + linear SVM people detector (fallback)", model=("hog", hog, None))
        return _DETECTOR["name"]
    except Exception as e:
        _DETECTOR["error"].append(f"opencv: {type(e).__name__}: {str(e)[:120]}")
    return None


def detect_people(rgb):
    """rgb: HxWx3 uint8 array → list of (x1, y1, x2, y2, score) for detected people."""
    kind, model, weights = _DETECTOR["model"]
    if kind == "torch":
        import torch
        t = torch.from_numpy(rgb).permute(2, 0, 1)
        with torch.no_grad():
            out = model([weights.transforms()(t)])[0]
        person = weights.meta["categories"].index("person")
        return [(*map(float, b), float(s)) for b, s, l in zip(out["boxes"], out["scores"], out["labels"])
                if int(l) == person and float(s) >= CV_SCORE_THRESHOLD]
    import cv2
    # HOG uses a fixed 64x128 window: small people need the full-size frame, large people a downscaled one
    h, w = rgb.shape[:2]
    hog_threshold = 0.5   # HOG scores are SVM margins, not probabilities
    keep = []
    for f in sorted({1.0, min(1.0, 480.0 / max(h, w))}):
        img = cv2.resize(rgb, (int(w * f), int(h * f))) if f < 1 else rgb
        rects, wts = model.detectMultiScale(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), winStride=(4, 4), padding=(8, 8), scale=1.05)
        keep += [(x / f, y / f, (x + bw) / f, (y + bh) / f, float(sc)) for (x, y, bw, bh), sc in zip(rects, np.ravel(wts))
                 if float(sc) >= hog_threshold]
    return _nms(keep)


def load_mobility_detector():
    """OWL-ViT (open-vocabulary, Hugging Face transformers). Returns its name, or None when it cannot load."""
    if _MOBILITY["name"] or _MOBILITY["error"]:
        return _MOBILITY["name"]
    try:
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        proc = AutoProcessor.from_pretrained(MOBILITY_MODEL_ID)
        model = AutoModelForZeroShotObjectDetection.from_pretrained(MOBILITY_MODEL_ID).to(dev).eval()
        prompts = [(cls, t) for cls, ts in MOBILITY_PROMPTS.items() for t in ts]
        _MOBILITY.update(name=f"OWL-ViT open-vocabulary detector ({MOBILITY_MODEL_ID}, {dev})", model=(proc, model, dev, prompts))
    except Exception as e:
        _MOBILITY["error"].append(f"mobility detector: {type(e).__name__}: {str(e)[:160]}")
    return _MOBILITY["name"]


def _inter(a, c):
    return max(0, min(a[2], c[2]) - max(a[0], c[0])) * max(0, min(a[3], c[3]) - max(a[1], c[1]))


def _area(a):
    return max(1e-9, (a[2] - a[0]) * (a[3] - a[1]))


def detect_mobility_aids(rgb, people=None):
    """rgb: HxWx3 uint8 array → list of (x1, y1, x2, y2, score, class) for wheelchairs, walkers, crutches, strollers.
    Three fixed rules (added in v8 after a run showed double counts and walkers on an empty path):
    1. overlapping boxes from different prompts are merged (the higher score wins);
    2. one object, one label: a box that lies mostly (≥ 60%) inside a higher-scoring aid box is the same object;
    3. a walker or crutches count only where they overlap a detected person (they are held while used).
    `people` is the person detector's boxes; when it is None, rule 3 is skipped."""
    import torch
    from PIL import Image
    proc, model, dev, prompts = _MOBILITY["model"]
    img = Image.fromarray(rgb)
    inputs = proc(text=[[t for _, t in prompts]], images=img, return_tensors="pt").to(dev)
    with torch.no_grad():
        out = model(**inputs)
    sizes = torch.tensor([img.size[::-1]], device=dev)
    post = getattr(proc, "post_process_object_detection", None) or proc.post_process_grounded_object_detection
    res = post(outputs=out, threshold=MOBILITY_SCORE_THRESHOLD, target_sizes=sizes)[0]
    found = [(*map(float, b), float(s), prompts[int(l)][0]) for b, s, l in zip(res["boxes"], res["scores"], res["labels"])]
    kept = _nms([f[:5] + (i,) for i, f in enumerate(found)])        # NMS on the boxes; the index carries the class along
    aids, merged = sorted((found[k[5]] for k in kept), key=lambda a: -a[4]), []
    for a in aids:                                                    # rule 2: one object, one label
        if all(_inter(a, m) / min(_area(a), _area(m)) < 0.6 for m in merged):
            merged.append(a)
    if people is not None:                                            # rule 3: held aids need a person
        merged = [a for a in merged if a[5] not in ("walker", "crutches")
                  or any(_inter(a, p) / _area(a) >= 0.2 for p in people)]
    return merged


def mobility_counts(aids):
    """Counts per class, plus the scored total (wheelchairs + walkers + crutches)."""
    per = {cls: sum(1 for a in aids if a[5] == cls) for cls in MOBILITY_PROMPTS}
    per["mobility_aid_riders"] = sum(per[c] for c in MOBILITY_AID_CLASSES)
    return per


def mobility_dataset():
    """The labelled wheelchair images as a DataFrame (image bytes + instances). Downloaded once; nothing derived is saved."""
    if _MOBILITY_DATA["df"] is not None or _MOBILITY_DATA["error"]:
        return _MOBILITY_DATA["df"]
    try:
        from huggingface_hub import list_repo_files, hf_hub_download
        files = [f for f in list_repo_files(MOBILITY_DATASET, repo_type="dataset") if f.endswith(".parquet")]
        rev = None
        if not files:                                        # some datasets keep parquet only on the converted branch
            rev = "refs/convert/parquet"
            files = [f for f in list_repo_files(MOBILITY_DATASET, repo_type="dataset", revision=rev) if f.endswith(".parquet")]
        parts = [pd.read_parquet(hf_hub_download(MOBILITY_DATASET, f, repo_type="dataset", revision=rev)) for f in sorted(files)]
        df = pd.concat(parts, ignore_index=True)
        df["n_wheelchairs"] = df["instances"].apply(lambda xs: sum(1 for x in xs if int(x["label"]) == 1))
        df["n_people"] = df["instances"].apply(lambda xs: sum(1 for x in xs if int(x["label"]) == 0))
        _MOBILITY_DATA["df"] = df
    except Exception as e:
        _MOBILITY_DATA["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    return _MOBILITY_DATA["df"]


def pick_accessible_demo(df):
    """Index of the image shown as the accessible stop camera: the first labelled wheelchair image (fixed shuffled order)
    in which the detector finds a wheelchair. The choice is recorded so V6 can leave it out of its accuracy test."""
    pool = df[(df["n_wheelchairs"] >= 1) & (df["n_people"] >= 1)]
    pool = (pool if len(pool) else df[df["n_wheelchairs"] >= 1]).sample(frac=1, random_state=11)
    chosen = int(pool.index[0])
    if _MOBILITY["name"]:
        for idx, row in pool.head(MOBILITY_DEMO_TRIES).iterrows():
            try:
                if any(a[5] == "wheelchair" for a in detect_mobility_aids(dataset_rgb(row))):
                    chosen = int(idx)
                    break
            except Exception:
                continue
    _MOBILITY_DATA["demo"] = chosen
    return chosen


def dataset_rgb(row):
    import cv2
    raw = row["image"]["bytes"] if isinstance(row["image"], dict) else row["image"]
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("unreadable dataset image")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _nms(boxes, iou=0.4):
    """Drop overlapping duplicate detections of the same person."""
    boxes = sorted(boxes, key=lambda b: -b[4])
    kept = []
    for b in boxes:
        def ov(a, c):
            ix = max(0, min(a[2], c[2]) - max(a[0], c[0])); iy = max(0, min(a[3], c[3]) - max(a[1], c[1]))
            inter = ix * iy
            return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (c[2] - c[0]) * (c[3] - c[1]) - inter + 1e-9)
        if all(ov(b, k) < iou for k in kept):
            kept.append(b)
    return kept


def _download(url):
    path = os.path.join(CV_DIR, os.path.basename(url))
    if not os.path.exists(path):
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    return path


def _frames(src, path):
    import cv2
    if src["kind"] == "dataset":
        df = mobility_dataset()
        if df is None:
            raise ValueError(f"dataset unavailable: {_MOBILITY_DATA['error']}")
        idx = pick_accessible_demo(df) if src.get("pick") == "visible_wheelchair" else int(df.index[0])
        yield idx, dataset_rgb(df.loc[idx])
        return
    if src["kind"] == "image":
        img = cv2.imread(path)
        if img is None:
            raise ValueError("unreadable image")
        yield 0, cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    for idx in np.linspace(0, n - 1, max(1, CV_VIDEO_FRAMES)).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if ok:
            yield int(idx), cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    cap.release()


def _privacy_preview(rgb, boxes, block=None, aids=()):
    """Privacy: the WHOLE frame is pixelated (so a person the detector missed is not identifiable either),
    then detection boxes are drawn on top. Display only; never saved or passed downstream."""
    import cv2
    h, w = rgb.shape[:2]
    block = block or max(12, w // 30)        # coarse enough that faces and clothing details cannot be made out
    small = cv2.resize(rgb, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA)
    out = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    for x1, y1, x2, y2, _ in boxes:
        cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), (250, 204, 21), max(2, w // 200))
    for x1, y1, x2, y2, _, cls in aids:                    # mobility aids in cyan, labelled with the object class only
        cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), (34, 211, 238), max(2, w // 200))
        cv2.putText(out, cls, (int(x1) + 4, max(14, int(y1) - 6)), cv2.FONT_HERSHEY_SIMPLEX, max(0.5, w / 1400), (34, 211, 238), 2)
    return out


def run_computer_vision(sources=CV_SOURCES):
    """Each camera → anonymized aggregate: people counted, load factor, detector confidence. No images or identities kept."""
    results = {"detector": None, "mobility_detector": None, "cameras": [], "errors": [], "ran_at": iso(utcnow()), "previews": []}
    if not USE_CV:
        results["errors"].append("computer vision disabled")
        return results
    results["detector"] = load_detector()
    if not results["detector"]:
        results["errors"] += _DETECTOR["error"]
        return results
    if USE_MOBILITY_AID_CV:
        results["mobility_detector"] = load_mobility_detector()
        results["errors"] += _MOBILITY["error"]
    for src in sources:
        try:
            path = None if src["kind"] == "dataset" else _download(src["url"])
            counts, confs, preview, aid_frames = [], [], None, []
            for idx, rgb in _frames(src, path):
                boxes = detect_people(rgb)
                aids = detect_mobility_aids(rgb, people=boxes) if results["mobility_detector"] else []
                counts.append(len(boxes))
                confs += [b[4] for b in boxes]
                aid_frames.append(mobility_counts(aids))
                if preview is None or len(boxes) + len(aids) > preview[1]:
                    preview = (_privacy_preview(rgb, boxes, aids=aids), len(boxes) + len(aids), idx, len(boxes), len(aids))
            if not counts:
                raise ValueError("no frames read")
            people = int(round(statistics.median(counts)))
            results["cameras"].append({
                "camera_id": src["camera_id"], "role": src["role"], "stop_id": src["stop_id"],
                "frames_analyzed": len(counts), "people_per_frame": counts, "person_count": people,
                "peak_count": max(counts), "capacity": src["capacity"], "load_factor": round(people / src["capacity"], 2),
                "mean_detector_score": round(float(np.mean(confs)), 2) if confs else None,   # probability for Faster R-CNN; SVM margin for HOG
                "observed_at": iso(utcnow()), "identities_stored": False, "images_stored": False, "note": src.get("note", ""),
            })
            cam = results["cameras"][-1]
            if results["mobility_detector"]:           # median over frames, like the person count
                cam["mobility_aids"] = {k: int(round(statistics.median(f[k] for f in aid_frames))) for k in aid_frames[0]}
                cam["mobility_aid_riders"] = cam["mobility_aids"].pop("mobility_aid_riders")
                cam["mobility_aids_per_frame"] = [f["mobility_aid_riders"] for f in aid_frames]
                xs = DEFAULT_POLICY["accessibility"]["extra_spaces"]
                cam["space_load_factor"] = round((cam["person_count"] + sum(n * xs.get(k, 0) for k, n in cam["mobility_aids"].items()))
                                                 / cam["capacity"], 2)
            else:
                cam["mobility_aids"], cam["mobility_aid_riders"], cam["mobility_aids_per_frame"] = None, None, []
            if SHOW_CV_PREVIEW and preview is not None:
                results["previews"].append((src["camera_id"], preview))
        except Exception as e:
            results["errors"].append(f"{src['camera_id']}: {type(e).__name__}: {str(e)[:120]}")
    return results


def show_cv_previews(results):
    if not results["previews"]:
        return
    fig, axes = plt.subplots(1, len(results["previews"]), figsize=(6 * len(results["previews"]), 5))
    axes = np.atleast_1d(axes)
    for ax, (cam, (img, n, idx, people, aids)) in zip(axes, results["previews"]):
        ax.imshow(img); ax.axis("off")
        ax.set_title(f"{cam}\n{people} {'person' if people == 1 else 'people'} (yellow) · {aids} mobility aid{'' if aids == 1 else 's'} (cyan) · "
                     f"frame {idx} · pixelated for privacy", fontsize=9)
    plt.tight_layout(); plt.show()


CV_RESULTS = run_computer_vision()
print("Person detector:", CV_RESULTS["detector"] or "unavailable")
print("Mobility-aid detector:", CV_RESULTS["mobility_detector"] or ("off" if not USE_MOBILITY_AID_CV else "unavailable"),
      f"(score threshold {MOBILITY_SCORE_THRESHOLD}, set before evaluation and not tuned on V6's test images)" if CV_RESULTS["mobility_detector"] else "")
for cam in CV_RESULTS["cameras"]:
    print(f"  {cam['camera_id']} ({cam['role']}): {cam['person_count']} counted (median of {cam['frames_analyzed']} frame(s), "
          f"peak {cam['peak_count']}), load factor {cam['load_factor']}, mean detector score {cam['mean_detector_score']}")
    if cam.get("mobility_aids") is not None:
        print(f"      mobility aids: {cam['mobility_aid_riders']} scored (" + ", ".join(f"{k} {v}" for k, v in cam["mobility_aids"].items())
              + f") · strollers take space but are not in W · space-adjusted load {cam['space_load_factor']} (load {cam['load_factor']})")
    print(f"      imagery: {cam['note']}")
for err in CV_RESULTS["errors"]:
    print("  ⚠️", err)
show_cv_previews(CV_RESULTS)
_ = CV_RESULTS.pop("previews", None)   # pixelated previews are display-only and are not carried into any case record
