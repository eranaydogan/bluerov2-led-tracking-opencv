#!/usr/bin/env python3
"""
LIDER / TAKIPCI POSE, ORYANTASYON ve YOL ANALIZI
Dinamik HUD + yaw tabanli 3D ok + anlik lider-takipci mesafesi
=================================================================

CSV formatı:
    time_s,x,y,z,yaw

Birim dönüşümü:
    CSV'deki x,y,z ve varsayılan leak-x/leak-z değerleri Unity birimidir.
    Varsayılan dönüşüm: 1 Unity unit = 1.175771 m.

Koordinat kabulü:
    Log x  -> görsel X ekseni
    Log z  -> görsel Y ekseni, yani ileri/geri Z düzlemi
    Log y  -> görsel Z ekseni, yani düşey/derinlik

Yaw kabulü:
    yaw =   0 derece -> +Z yönü
    yaw =  90 derece -> +X yönü
    yaw = 180 derece -> -Z yönü
    yaw = 270 derece -> -X yönü

Yaw kalibrasyonu:
    Eğer Unity/Unreal/Gazebo tarafında robot gövde mesh'i loglanan yaw'a göre sabit
    açısal offset ile yerleştirilmişse CSV dosyasına dokunmadan şu argümanlar kullanılır:
        --leader-yaw-offset 90
        --follower-yaw-offset 0

Örnek kullanım:
    python path_analysis_final_unity_scale.py \
        --leader leader_path_log.csv \
        --follower follower_path_log.csv \
        --out path_analysis \
        --leak-x -114.991 \
        --leak-z 871.2 \
        --unity-to-meter 1.175771

Çıktılar:
    path_analysis_dashboard.html
    path_analysis_1_top_view.png
    path_analysis_2_depth_time.png
    path_analysis_3_separation_time.png
    path_analysis_4_target_error_time.png
    path_analysis_metrics.json
"""

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    print("[UYARI] 'plotly' kütüphanesi bulunamadı. İnteraktif HTML üretilmeyecek.")


LEAK_X = -114.991
LEAK_Z = 871.2
UNITY_TO_METER = 1.175771

PHASE_NORMAL = 0
PHASE_ASCEND = 1
PHASE_HOVER = 2

# Akademik/açık tema renkleri
LEADER_COLOR = "#2563eb"       # mavi
FOLLOWER_COLOR = "#059669"     # yeşil
TARGET_COLOR = "#f59e0b"       # amber
ASCEND_COLOR = "#dc2626"       # kırmızı
TEXT_COLOR = "#111827"
MUTED_TEXT_COLOR = "#6b7280"
GRID_COLOR = "#e5e7eb"
PANEL_BORDER_COLOR = "#d1d5db"
PAGE_BG = "#f8fafc"
PANEL_BG = "rgba(255, 255, 255, 0.94)"


def parse_args():
    ap = argparse.ArgumentParser(description="Lider/Takipci pose-oryantasyon analizi + dinamik gorsel")
    ap.add_argument("--leader", required=True, help="leader_path_log.csv yolu")
    ap.add_argument("--follower", required=True, help="follower_path_log.csv yolu")
    ap.add_argument("--leak-x", type=float, default=LEAK_X,
                    help="Sızıntı/hedef X konumu. Varsayılan olarak Unity birimi kabul edilir ve metreye çevrilir.")
    ap.add_argument("--leak-z", type=float, default=LEAK_Z,
                    help="Sızıntı/hedef Z konumu. Varsayılan olarak Unity birimi kabul edilir ve metreye çevrilir.")
    ap.add_argument("--unity-to-meter", type=float, default=UNITY_TO_METER,
                    help="Unity koordinatlarını metreye çevirmek için ölçek katsayısı. Varsayılan: 1 Unity unit = 1.175771 m")
    ap.add_argument("--leak-coords-meter", action="store_true",
                    help="Bu seçenek verilirse --leak-x/--leak-z zaten metre kabul edilir; tekrar unity-to-meter ile çarpılmaz.")
    ap.add_argument("--out", default="path_analysis", help="Cikti oneki/yolu")

    # Faz sınıflandırması artık örnek başı mesafe yerine hızla yapılır.
    ap.add_argument("--still-speed-eps", type=float, default=0.0001,
                    help="Yatayda hareketsiz kabul edilecek XZ hız eşiği [m/s]")
    ap.add_argument("--ascend-speed-eps", type=float, default=0.03,
                    help="Yukarı çıkış kabul edilecek dY/dt eşiği [m/s]. Negatif derinlikte yüzeye çıkış için y artar.")
    ap.add_argument("--min-phase-len", type=int, default=5,
                    help="Kısa faz bloklarını bastırmak için minimum örnek sayısı")
    ap.add_argument("--no-ascend-latch", action="store_true",
                    help="Varsayılan davranış: ASCEND bir kez tespit edilince görev sonuna kadar ASCEND kalır. Bu seçenek kilidi kapatır.")

    ap.add_argument("--frames", type=int, default=220, help="Animasyon kare sayısı")
    ap.add_argument("--arrow-size", type=float, default=3.0, help="3D yön oklarının uzunluğu")
    ap.add_argument("--speed-display-scale", type=float, default=0.5,
                    help="Sadece HUD'da gösterilen hızları çarpar. Varsayılan 0.5: hızları ikiye böler. Mesafe/yol metriklerini değiştirmez.")
    ap.add_argument("--hide-speed", action="store_true",
                    help="HUD'daki Lider/Takipçi Hız satırını tamamen gizler.")
    ap.add_argument("--depth-display-max", type=float, default=130.0,
                    help="Derinlik gösterimi için üst sınır [m]. Varsayılan: BlueROV2 için 130 m.")
    ap.add_argument("--no-depth-normalize", action="store_true",
                    help="Derinlikleri 130 m tavanına göre normalize etmeden gösterir.")

    # Görselleştirme kalibrasyonu. CSV dosyasını değiştirmez; sadece log okunup yorumlanırken uygulanır.
    ap.add_argument("--leader-yaw-offset", type=float, default=0.0,
                    help="Lider yaw değerine eklenecek sabit kalibrasyon açısı [deg]. Örn: lider 90° sola kayık görünüyorsa çoğunlukla +90.")
    ap.add_argument("--follower-yaw-offset", type=float, default=0.0,
                    help="Takipçi yaw değerine eklenecek sabit kalibrasyon açısı [deg].")

    ap.add_argument("--offline-html", action="store_true",
                    help="Plotly JS dosyasını HTML içine göm. Jüri/demo için internet gerektirmez; dosya büyür.")
    ap.add_argument("--show-negative-depth", action="store_true",
                    help="HUD/grafiklerde derinliği logdaki işaretiyle göster. Varsayılan: abs(y) ile pozitif derinlik.")
    return ap.parse_args()


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_path(csv_path, unity_to_meter=UNITY_TO_METER):
    """
    CSV okuyucu. Beklenen zorunlu kolonlar: time_s,x,y,z,yaw.
    Eksik yaw varsa 0 kabul edilir. Zaman sıralanır ve tekrar eden timestamp'ler ayıklanır.
    x,y,z Unity biriminden metreye çevrilir; yaw derece olarak kalır.
    """
    t, x, y, z, yaw = [], [], [], [], []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                t.append(float(row["time_s"]))
                x.append(float(row["x"]))
                y.append(float(row["y"]))
                z.append(float(row["z"]))
                yaw.append(_safe_float(row.get("yaw", 0.0), 0.0))
            except (ValueError, KeyError):
                # Bozuk satır varsa tüm analizi durdurmak yerine atla.
                continue

    if len(t) == 0:
        return {"t": np.array([]), "x": np.array([]), "y": np.array([]), "z": np.array([]), "yaw": np.array([])}

    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    yaw = np.asarray(yaw, dtype=float)

    order = np.argsort(t)
    t, x, y, z, yaw = t[order], x[order], y[order], z[order], yaw[order]

    # np.interp tekrar eden timestamp'lerde problem çıkarabilir; ilk görülen timestamp tutulur.
    t_unique, idx = np.unique(t, return_index=True)
    x, y, z, yaw = x[idx], y[idx], z[idx], yaw[idx]

    scale = float(unity_to_meter)
    x = x * scale
    y = y * scale
    z = z * scale

    return {"t": t_unique, "x": x, "y": y, "z": z, "yaw": yaw}


def interpolate_angle_deg(t_new, t_src, yaw_deg_src):
    """Yaw açısını wrap sorunu olmadan interpolate eder."""
    yaw_rad = np.unwrap(np.deg2rad(yaw_deg_src))
    yaw_interp_rad = np.interp(t_new, t_src, yaw_rad)
    return np.rad2deg(yaw_interp_rad)


def normalize_angle_360(angle_deg):
    """HUD için açıyı 0-360 aralığına indirger."""
    return np.mod(angle_deg, 360.0)


def apply_yaw_offset(yaw_deg, offset_deg):
    """
    CSV'yi değiştirmeden sabit gövde/mesh hizalama hatasını düzeltir.

    corrected_yaw = raw_yaw + offset_deg

    Örnek:
        Logda lider yaw=90° başlıyor ama gerçek/görsel baş yönü -Z ise
        yaw=180° olmalıdır. Bu durumda offset +90° verilir.
    """
    return np.asarray(yaw_deg, dtype=float) + float(offset_deg)


def yaw_to_dir(yaw_deg, arr_size=3.0):
    """
    Log/görsel convention'a göre yaw -> Plotly Cone vektörü.

    Plotly eksenleri:
        x : log X
        y : log Z
        z : log Y

    Yaw kabulü:
        0   deg -> +Z
        90  deg -> +X
        180 deg -> -Z
        270 deg -> -X
    """
    yaw_rad = np.deg2rad(yaw_deg)
    u = np.sin(yaw_rad) * arr_size       # Plotly x ekseni = log X
    v = np.cos(yaw_rad) * arr_size       # Plotly y ekseni = log Z
    w = np.zeros_like(u, dtype=float)    # pitch/roll yoksa dikey yön bileşeni çizilmez
    return u, v, w


def smooth_short_blocks(labels, min_phase_len):
    if len(labels) == 0 or min_phase_len <= 1:
        return labels

    labels = labels.copy()
    blocks = []
    start = 0
    for k in range(1, len(labels)):
        if labels[k] != labels[k - 1]:
            blocks.append((start, k - 1, labels[start]))
            start = k
    blocks.append((start, len(labels) - 1, labels[start]))

    for bi, (s, e, lab) in enumerate(blocks):
        if (e - s + 1) < min_phase_len:
            if bi > 0:
                labels[s:e + 1] = blocks[bi - 1][2]
            elif len(blocks) > 1:
                labels[s:e + 1] = blocks[bi + 1][2]
    return labels


def latch_ascend_state(labels):
    """
    ASCEND bir acil durum/failsafe olduğu için bir kez tespit edildikten sonra
    görev bitene kadar geri TAKİP moduna dönmemesi gerekir.
    """
    labels = labels.copy()
    ascend_idx = np.where(labels == PHASE_ASCEND)[0]
    if len(ascend_idx) > 0:
        first = int(ascend_idx[0])
        labels[first:] = PHASE_ASCEND
    return labels


def classify_phases(p, still_speed_eps, ascend_speed_eps, min_phase_len, latch_ascend=True):
    """
    Faz sınıflandırması:
        0 NORMAL : yatay hareket var veya ascend/hover değil
        1 ASCEND : yatay hız düşük ve y artış hızı pozitif/yeterli
        2 HOVER  : yatay hız düşük ve dikey hız da düşük

    Not:
        Verilen logda y negatif derinlik gibi görünüyor.
        Bu durumda yüzeye çıkış y'nin artmasıdır: -145 -> -144 gibi.
    """
    n = len(p["x"])
    labels = np.zeros(n, dtype=int)
    if n < 2:
        return labels

    dt = np.diff(p["t"])
    dt = np.maximum(dt, 1e-6)

    vxz = np.hypot(np.diff(p["x"]), np.diff(p["z"])) / dt
    vy = np.diff(p["y"]) / dt

    step_label = np.zeros(n - 1, dtype=int)
    horiz_still = vxz <= still_speed_eps
    rising = vy > ascend_speed_eps
    vertical_still = np.abs(vy) <= ascend_speed_eps

    step_label[horiz_still & rising] = PHASE_ASCEND
    #step_label[horiz_still & vertical_still] = PHASE_HOVER

    labels[:n - 1] = step_label
    labels[n - 1] = step_label[-1]

    labels = smooth_short_blocks(labels, min_phase_len)

    if latch_ascend:
        labels = latch_ascend_state(labels)

    return labels


def sample_labels_at_time(t_new, t_src, labels):
    idx = np.searchsorted(t_src, t_new, side="right") - 1
    idx = np.clip(idx, 0, len(labels) - 1)
    return labels[idx]


def path_length_xz(x, z, mask=None):
    xs, zs = (x, z) if mask is None else (x[mask], z[mask])
    if len(xs) < 2:
        return 0.0
    return float(np.sum(np.hypot(np.diff(xs), np.diff(zs))))


def path_length_3d(x, y, z, mask=None):
    xs, ys, zs = (x, y, z) if mask is None else (x[mask], y[mask], z[mask])
    if len(xs) < 2:
        return 0.0
    return float(np.sum(np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2 + np.diff(zs) ** 2)))


def cumulative_path_xz(x, z):
    if len(x) == 0:
        return np.array([])
    if len(x) == 1:
        return np.array([0.0])
    step = np.hypot(np.diff(x), np.diff(z))
    return np.concatenate([[0.0], np.cumsum(step)])


def speed_3d(t, x, y, z):
    if len(t) < 2:
        return np.zeros_like(t)
    vx = np.gradient(x, t)
    vy = np.gradient(y, t)
    vz = np.gradient(z, t)
    return np.sqrt(vx ** 2 + vy ** 2 + vz ** 2)


def depth_display(y, show_negative_depth=False, depth_scale=1.0):
    """Sadece gösterim amaçlı derinlik dönüşümü."""
    y_disp = y if show_negative_depth else np.abs(y)
    return y_disp * float(depth_scale)


def compute_depth_display_scale(pl, pf, args):
    """BlueROV2 maksimum derinliği gibi görsel tavanlara göre derinlik gösterimini ölçekler."""
    raw_max_depth = float(max(np.max(np.abs(pl["y"])), np.max(np.abs(pf["y"]))))
    if args.no_depth_normalize:
        return 1.0, raw_max_depth
    max_display = float(args.depth_display_max)
    if max_display <= 0:
        return 1.0, raw_max_depth
    if raw_max_depth > max_display:
        return max_display / raw_max_depth, raw_max_depth
    return 1.0, raw_max_depth


def phase_to_text(label):
    if int(label) == PHASE_ASCEND:
        return "EMERGENCY: ASCEND"
    if int(label) == PHASE_HOVER:
        return "HOLD"
    return "TRACKING"


def phase_to_color(label):
    if int(label) == PHASE_ASCEND:
        return ASCEND_COLOR
    if int(label) == PHASE_HOVER:
        return TARGET_COLOR
    return LEADER_COLOR


def build_common_animation_data(pl, pf, lab_f, args):
    t0 = max(pl["t"][0], pf["t"][0])
    t1 = min(pl["t"][-1], pf["t"][-1])
    if t1 <= t0:
        # Loglar hiç çakışmıyorsa yine de eski davranışa düş, ama uyarı ver.
        print("[UYARI] Lider ve takipçi zaman aralıkları çakışmıyor. Tüm aralık üzerinden interpolate edilecek.")
        t0 = min(pl["t"][0], pf["t"][0])
        t1 = max(pl["t"][-1], pf["t"][-1])

    num_frames = max(10, int(args.frames))
    t_anim = np.linspace(t0, t1, num_frames)

    xl = np.interp(t_anim, pl["t"], pl["x"])
    yl = np.interp(t_anim, pl["t"], pl["y"])
    zl = np.interp(t_anim, pl["t"], pl["z"])
    yaw_l_raw = interpolate_angle_deg(t_anim, pl["t"], pl["yaw"])
    yaw_l = apply_yaw_offset(yaw_l_raw, args.leader_yaw_offset)

    xf = np.interp(t_anim, pf["t"], pf["x"])
    yf = np.interp(t_anim, pf["t"], pf["y"])
    zf = np.interp(t_anim, pf["t"], pf["z"])
    yaw_f_raw = interpolate_angle_deg(t_anim, pf["t"], pf["yaw"])
    yaw_f = apply_yaw_offset(yaw_f_raw, args.follower_yaw_offset)

    u_l, v_l, w_l = yaw_to_dir(yaw_l, args.arrow_size)
    u_f, v_f, w_f = yaw_to_dir(yaw_f, args.arrow_size)

    sep_3d = np.sqrt((xl - xf) ** 2 + (yl - yf) ** 2 + (zl - zf) ** 2)
    sep_xz = np.hypot(xl - xf, zl - zf)
    leak_err = np.hypot(xf - args.leak_x, zf - args.leak_z)

    leader_cum_xz = cumulative_path_xz(xl, zl)
    follower_cum_xz = cumulative_path_xz(xf, zf)
    leader_speed = speed_3d(t_anim, xl, yl, zl)
    follower_speed = speed_3d(t_anim, xf, yf, zf)

    phase_anim = sample_labels_at_time(t_anim, pf["t"], lab_f)

    return {
        "t": t_anim,
        "xl": xl, "yl": yl, "zl": zl, "yaw_l": yaw_l, "yaw_l_raw": yaw_l_raw,
        "xf": xf, "yf": yf, "zf": zf, "yaw_f": yaw_f, "yaw_f_raw": yaw_f_raw,
        "u_l": u_l, "v_l": v_l, "w_l": w_l,
        "u_f": u_f, "v_f": v_f, "w_f": w_f,
        "sep_3d": sep_3d,
        "sep_xz": sep_xz,
        "leak_err": leak_err,
        "leader_cum_xz": leader_cum_xz,
        "follower_cum_xz": follower_cum_xz,
        "leader_speed": leader_speed,
        "follower_speed": follower_speed,
        "phase": phase_anim,
        "t0": float(t0),
        "t1": float(t1),
    }


def make_metrics(pl, pf, anim, lab_f, args):
    leader_total_xz = path_length_xz(pl["x"], pl["z"])
    follower_total_xz = path_length_xz(pf["x"], pf["z"])
    leader_total_3d = path_length_3d(pl["x"], pl["y"], pl["z"])
    follower_total_3d = path_length_3d(pf["x"], pf["y"], pf["z"])

    sep_3d = anim["sep_3d"]
    sep_xz = anim["sep_xz"]
    leak_err = anim["leak_err"]

    # Takip performansı metrikleri acil çıkıştan önceki bölümden hesaplanır.
    # ASCEND başladıktan sonra takipçi artık takip görevinde olmadığı için bu bölüm
    # ortalama/maksimum lider-takipçi mesafesini yapay olarak büyütür.
    tracking_mask = anim["phase"] != PHASE_ASCEND
    if not np.any(tracking_mask):
        # Nadir durumda animasyonun tamamı ASCEND olarak etiketlenirse NaN üretmemek için
        # tüm seri fallback olarak kullanılır.
        tracking_mask = np.ones_like(sep_3d, dtype=bool)

    sep_3d_tracking = sep_3d[tracking_mask]
    sep_xz_tracking = sep_xz[tracking_mask]

    ascend_idx = np.where(lab_f == PHASE_ASCEND)[0]
    asc_start_t = float(pf["t"][ascend_idx[0]]) if len(ascend_idx) > 0 else None
    if len(ascend_idx) > 0:
        gx = float(pf["x"][ascend_idx[0]])
        gz = float(pf["z"][ascend_idx[0]])
    else:
        gx = float(pf["x"][-1])
        gz = float(pf["z"][-1])
    ascend_or_final_leak_error = float(math.hypot(gx - args.leak_x, gz - args.leak_z))

    raw_max_depth_abs = float(max(np.max(np.abs(pl["y"])), np.max(np.abs(pf["y"]))))
    depth_display_scale = float(getattr(args, "depth_display_scale", 1.0))
    max_depth_abs = raw_max_depth_abs * depth_display_scale
    min_y = float(min(np.min(pl["y"]), np.min(pf["y"])))

    return {
        "coordinate_convention": {
            "visual_x": "log x",
            "visual_y": "log z",
            "visual_z": "log y",
            "yaw_0_deg": "+Z",
            "yaw_90_deg": "+X",
            "yaw_180_deg": "-Z",
            "yaw_270_deg": "-X",
            "leader_yaw_offset_deg": float(args.leader_yaw_offset),
            "follower_yaw_offset_deg": float(args.follower_yaw_offset),
            "yaw_used_in_dashboard": "corrected_yaw = raw_yaw + yaw_offset",
            "position_source_unit": "Unity unit",
            "position_output_unit": "meter",
            "unity_to_meter": float(args.unity_to_meter),
            "leak_coordinates_already_meter": bool(args.leak_coords_meter),
        },
        "sync_start_s": float(anim["t0"]),
        "sync_end_s": float(anim["t1"]),
        "sync_duration_s": float(anim["t1"] - anim["t0"]),
        "speed_display_scale": float(args.speed_display_scale),
        "speed_display_note": "Only HUD speed values are multiplied by this factor; distance/path metrics are unchanged.",
        "leader_total_path_xz_m": float(leader_total_xz),
        "follower_total_path_xz_m": float(follower_total_xz),
        "leader_total_path_3d_m": float(leader_total_3d),
        "follower_total_path_3d_m": float(follower_total_3d),
        "max_abs_depth_m": max_depth_abs,
        "raw_max_abs_depth_m": raw_max_depth_abs,
        "depth_display_scale": depth_display_scale,
        "depth_display_max_m": float(getattr(args, "depth_display_max", 130.0)),
        "minimum_y_value_m": min_y,
        # Ana takip performansı metrikleri: sadece ASCEND öncesi takip bölümü.
        "leader_follower_distance_3d": {
            "scope": "tracking_only_excluding_ascend",
            "mean_m": float(np.mean(sep_3d_tracking)),
            "rms_m": float(np.sqrt(np.mean(sep_3d_tracking ** 2))),
            "max_m": float(np.max(sep_3d_tracking)),
            "final_tracking_m": float(sep_3d_tracking[-1]),
        },
        "leader_follower_distance_xz": {
            "scope": "tracking_only_excluding_ascend",
            "mean_m": float(np.mean(sep_xz_tracking)),
            "rms_m": float(np.sqrt(np.mean(sep_xz_tracking ** 2))),
            "max_m": float(np.max(sep_xz_tracking)),
            "final_tracking_m": float(sep_xz_tracking[-1]),
        },
        # Referans için tüm görev boyunca mesafe de ayrıca saklanır. Dashboard özetinde kullanılmaz.
        "leader_follower_distance_3d_full_mission": {
            "scope": "full_mission_including_ascend",
            "mean_m": float(np.mean(sep_3d)),
            "rms_m": float(np.sqrt(np.mean(sep_3d ** 2))),
            "max_m": float(np.max(sep_3d)),
            "final_m": float(sep_3d[-1]),
        },
        "leader_follower_distance_xz_full_mission": {
            "scope": "full_mission_including_ascend",
            "mean_m": float(np.mean(sep_xz)),
            "rms_m": float(np.sqrt(np.mean(sep_xz ** 2))),
            "max_m": float(np.max(sep_xz)),
            "final_m": float(sep_xz[-1]),
        },
        "follower_to_leak_error_xz": {
            "mean_m": float(np.mean(leak_err)),
            "min_m": float(np.min(leak_err)),
            "final_m": float(leak_err[-1]),
            "ascend_start_or_final_m": ascend_or_final_leak_error,
        },
        "ascend": {
            "detected": bool(len(ascend_idx) > 0),
            "start_time_s": asc_start_t,
        },
    }


def write_metrics_json(metrics, out_prefix):
    path = out_prefix + "_metrics.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"[OK] Metrikler yazıldı: {path}")


def make_plotly_dashboard(pl, pf, anim, metrics, args, out_prefix):
    if not HAS_PLOTLY:
        return

    print("\n[INFO] Dinamik Plotly dashboard oluşturuluyor...")

    xl, yl, zl = anim["xl"], anim["yl"], anim["zl"]
    xf, yf, zf = anim["xf"], anim["yf"], anim["zf"]
    u_l, v_l, w_l = anim["u_l"], anim["v_l"], anim["w_l"]
    u_f, v_f, w_f = anim["u_f"], anim["v_f"], anim["w_f"]
    t_anim = anim["t"]
    phase_anim = anim["phase"]
    num_frames = len(t_anim)

    # Derinlik sadece görsel eksende normalize edilir. X-Z konum ve metrikler korunur.
    depth_scale = float(getattr(args, "depth_display_scale", 1.0))
    pl_y_plot = pl["y"] * depth_scale
    pf_y_plot = pf["y"] * depth_scale
    yl_plot = yl * depth_scale
    yf_plot = yf * depth_scale

    min_x = float(min(np.min(pl["x"]), np.min(pf["x"]), args.leak_x))
    max_x = float(max(np.max(pl["x"]), np.max(pf["x"]), args.leak_x))
    min_z = float(min(np.min(pl["z"]), np.min(pf["z"]), args.leak_z))
    max_z = float(max(np.max(pl["z"]), np.max(pf["z"]), args.leak_z))
    min_y = float(min(np.min(pl_y_plot), np.min(pf_y_plot)))

    pad = 10.0
    grid_x = np.array([[min_x - pad, max_x + pad], [min_x - pad, max_x + pad]])
    grid_z = np.array([[min_z - pad, min_z - pad], [max_z + pad, max_z + pad]])
    grid_y_water = np.zeros((2, 2))
    grid_y_bottom = np.full((2, 2), min_y - 2.0)

    fig = go.Figure()

    # 0-1. Tam rota, düşük opaklıkta referans yol.
    fig.add_trace(go.Scatter3d(
        x=pl["x"], y=pl["z"], z=pl_y_plot, mode="lines",
        line=dict(color="rgba(0, 0, 0, 0.45)", width=2, dash="dash"),
        name="Leader Full Path", hoverinfo="skip"
    ))
    fig.add_trace(go.Scatter3d(
        x=pf["x"], y=pf["z"], z=pf_y_plot, mode="lines",
        line=dict(color="rgba(0, 0, 0, 0.45)", width=2, dash="dash"),
        name="Follower Full Path", hoverinfo="skip"
    ))

    # 2-3. Animasyonla uzayan neon trail.
    fig.add_trace(go.Scatter3d(
        x=[xl[0]], y=[zl[0]], z=[yl_plot[0]], mode="lines",
        name="Leader Trail", line=dict(color=LEADER_COLOR, width=6)
    ))
    fig.add_trace(go.Scatter3d(
        x=[xf[0]], y=[zf[0]], z=[yf_plot[0]], mode="lines",
        name="Follower Trail", line=dict(color=FOLLOWER_COLOR, width=6)
    ))

    # 4-5. Yaw tabanlı yön okları.
    fig.add_trace(go.Cone(
        x=[xl[0]], y=[zl[0]], z=[yl_plot[0]],
        u=[u_l[0]], v=[v_l[0]], w=[w_l[0]],
        sizemode="absolute", sizeref=max(0.5, args.arrow_size * 1.2),
        showscale=False, colorscale=[[0, LEADER_COLOR], [1, LEADER_COLOR]],
        name="Leader Heading"
    ))
    fig.add_trace(go.Cone(
        x=[xf[0]], y=[zf[0]], z=[yf_plot[0]],
        u=[u_f[0]], v=[v_f[0]], w=[w_f[0]],
        sizemode="absolute", sizeref=max(0.5, args.arrow_size * 1.2),
        showscale=False, colorscale=[[0, FOLLOWER_COLOR], [1, FOLLOWER_COLOR]],
        name="Follower Heading"
    ))

    # 6-7. Anlık araç marker'ları.
    fig.add_trace(go.Scatter3d(
        x=[xl[0]], y=[zl[0]], z=[yl_plot[0]], mode="markers+text",
        marker=dict(size=5, color=LEADER_COLOR),
        text=["Leader"], textposition="top center", textfont=dict(color=LEADER_COLOR),
        name="Leader Current"
    ))
    fig.add_trace(go.Scatter3d(
        x=[xf[0]], y=[zf[0]], z=[yf_plot[0]], mode="markers+text",
        marker=dict(size=5, color=FOLLOWER_COLOR),
        text=["Follower"], textposition="top center", textfont=dict(color=FOLLOWER_COLOR),
        name="Follower Current"
    ))

    # 8. Lider-takipçi anlık mesafe çizgisi.
    fig.add_trace(go.Scatter3d(
        x=[xl[0], xf[0]], y=[zl[0], zf[0]], z=[yl_plot[0], yf_plot[0]], mode="lines",
        line=dict(color="rgba(71, 85, 105, 0.75)", width=4, dash="dash"),
        name="Current Separation"
    ))

    # 9. Su yüzeyi.
    fig.add_trace(go.Surface(
        x=grid_x, y=grid_z, z=grid_y_water,
        colorscale=[[0, "rgba(125, 211, 252, 0.18)"], [1, "rgba(125, 211, 252, 0.18)"]],
        showscale=False, name="Water Surface", hoverinfo="skip"
    ))

    # 10. Zemin.
    fig.add_trace(go.Surface(
        x=grid_x, y=grid_z, z=grid_y_bottom,
        colorscale=[[0, "rgba(203, 213, 225, 0.55)"], [1, "rgba(203, 213, 225, 0.55)"]],
        showscale=False, name="Seabed", hoverinfo="skip"
    ))

    # 11. Leak/hedef.
    fig.add_trace(go.Scatter3d(
        x=[args.leak_x], y=[args.leak_z], z=[min_y - 1.0],
        mode="markers+text", name="Target",
        text=["TARGET"], textposition="top center", textfont=dict(color=TARGET_COLOR, size=14),
        marker=dict(color=TARGET_COLOR, size=8, symbol="diamond")
    ))

    frames = []
    for k in range(num_frames):
        frames.append(go.Frame(
            data=[
                go.Scatter3d(x=xl[:k + 1], y=zl[:k + 1], z=yl_plot[:k + 1]),
                go.Scatter3d(x=xf[:k + 1], y=zf[:k + 1], z=yf_plot[:k + 1]),
                go.Cone(x=[xl[k]], y=[zl[k]], z=[yl_plot[k]], u=[u_l[k]], v=[v_l[k]], w=[w_l[k]]),
                go.Cone(x=[xf[k]], y=[zf[k]], z=[yf_plot[k]], u=[u_f[k]], v=[v_f[k]], w=[w_f[k]]),
                go.Scatter3d(x=[xl[k]], y=[zl[k]], z=[yl_plot[k]], text=["Leader"]),
                go.Scatter3d(x=[xf[k]], y=[zf[k]], z=[yf_plot[k]], text=["Follower"]),
                go.Scatter3d(x=[xl[k], xf[k]], y=[zl[k], zf[k]], z=[yl_plot[k], yf_plot[k]]),
            ],
            traces=[2, 3, 4, 5, 6, 7, 8],
            name=str(k)
        ))
    fig.frames = frames

    timeline_steps = []
    step_stride = max(1, num_frames // 80)  # Çok fazla frame varsa slider kalabalıklaşmasın.
    for k in range(0, num_frames, step_stride):
        timeline_steps.append(dict(
            method="animate",
            args=[[str(k)], dict(frame=dict(duration=0, redraw=True), mode="immediate", transition=dict(duration=0))],
            label=f"{t_anim[k]:.0f}s"
        ))

    fig.update_layout(
        template="plotly_white",
        margin=dict(l=0, r=0, b=0, t=0),
        paper_bgcolor=PAGE_BG,
        plot_bgcolor="#ffffff",
        font=dict(color=TEXT_COLOR),
        scene=dict(
            xaxis_title="X [m]",
            yaxis_title="Z [m]",
            zaxis_title="Depth [m]",
            bgcolor=PAGE_BG,
            xaxis=dict(
                showbackground=True,
                backgroundcolor="#ffffff",
                gridcolor=GRID_COLOR,
                zerolinecolor="#9ca3af",
                color=TEXT_COLOR,
            ),
            yaxis=dict(
                showbackground=True,
                backgroundcolor="#ffffff",
                gridcolor=GRID_COLOR,
                zerolinecolor="#9ca3af",
                color=TEXT_COLOR,
            ),
            zaxis=dict(
                showbackground=True,
                backgroundcolor="#ffffff",
                gridcolor=GRID_COLOR,
                zerolinecolor="#9ca3af",
                color=TEXT_COLOR,
            ),
            aspectmode="manual",
            aspectratio=dict(x=1, y=1, z=0.45)
        ),
        sliders=[
            dict(
                active=0,
                yanchor="bottom", xanchor="center", y=0.095, x=0.5,
                pad=dict(b=10, t=10), len=0.58,
                currentvalue=dict(
                    font=dict(size=13, color=LEADER_COLOR),
                    prefix="Time: ",
                    suffix="",
                    visible=True,
                    xanchor="center"
                ),
                steps=timeline_steps,
                bgcolor="rgba(255, 255, 255, 0.92)",
                bordercolor=PANEL_BORDER_COLOR,
                font=dict(color=TEXT_COLOR)
            )
        ]
    )

    include_plotlyjs = True if args.offline_html else "cdn"
    plot_div = fig.to_html(full_html=False, include_plotlyjs=include_plotlyjs)

    hud_time = anim["t"].tolist()
    hud_leader_depth = depth_display(anim["yl"], args.show_negative_depth, getattr(args, "depth_display_scale", 1.0)).tolist()
    hud_follower_depth = depth_display(anim["yf"], args.show_negative_depth, getattr(args, "depth_display_scale", 1.0)).tolist()
    hud_sep_3d = anim["sep_3d"].tolist()
    hud_sep_xz = anim["sep_xz"].tolist()
    hud_leak = anim["leak_err"].tolist()
    hud_state = [phase_to_text(v) for v in phase_anim]
    hud_state_color = [phase_to_color(v) for v in phase_anim]
    hud_yaw_l = normalize_angle_360(anim["yaw_l"]).tolist()
    hud_yaw_f = normalize_angle_360(anim["yaw_f"]).tolist()
    hud_leader_cum = anim["leader_cum_xz"].tolist()
    hud_follower_cum = anim["follower_cum_xz"].tolist()
    # Görsel hız kalibrasyonu: yalnızca HUD'da gösterilen hızlara uygulanır.
    # Konum, mesafe, yol ve takip metrikleri bundan etkilenmez.
    speed_display_scale = float(args.speed_display_scale)
    hud_leader_speed = (anim["leader_speed"] * speed_display_scale).tolist()
    hud_follower_speed = (anim["follower_speed"] * speed_display_scale).tolist()

    # JSON verisini HTML içine güvenli göm.
    hud_payload = {
        "time": hud_time,
        "leaderDepth": hud_leader_depth,
        "followerDepth": hud_follower_depth,
        "sep3d": hud_sep_3d,
        "sepXz": hud_sep_xz,
        "leak": hud_leak,
        "state": hud_state,
        "stateColor": hud_state_color,
        "yawLeader": hud_yaw_l,
        "yawFollower": hud_yaw_f,
        "yawLeaderRaw": normalize_angle_360(anim["yaw_l_raw"]).tolist(),
        "yawFollowerRaw": normalize_angle_360(anim["yaw_f_raw"]).tolist(),
        "leaderCum": hud_leader_cum,
        "followerCum": hud_follower_cum,
        "leaderSpeed": hud_leader_speed,
        "followerSpeed": hud_follower_speed,
        "speedDisplayScale": speed_display_scale,
        "hideSpeed": bool(args.hide_speed),
    }

    hud_script = f"""
    <script>
    const HUD = {json.dumps(hud_payload, ensure_ascii=False)};

    function fmt(value, digits) {{
        if (value === null || value === undefined || Number.isNaN(value)) return "-";
        return Number(value).toFixed(digits);
    }}

    function updateHUD(k) {{
        k = Math.max(0, Math.min(k, HUD.time.length - 1));

        document.getElementById("hud-time").textContent = fmt(HUD.time[k], 1);
        document.getElementById("hud-leader-depth").textContent = fmt(HUD.leaderDepth[k], 1);
        document.getElementById("hud-follower-depth").textContent = fmt(HUD.followerDepth[k], 1);
        document.getElementById("hud-sep3d").textContent = fmt(HUD.sep3d[k], 2);
        document.getElementById("hud-sepxz").textContent = fmt(HUD.sepXz[k], 2);
        document.getElementById("hud-leak").textContent = fmt(HUD.leak[k], 2);
        document.getElementById("hud-yaw-leader").textContent = fmt(HUD.yawLeader[k], 1);
        document.getElementById("hud-yaw-follower").textContent = fmt(HUD.yawFollower[k], 1);
        document.getElementById("hud-leader-cum").textContent = fmt(HUD.leaderCum[k], 1);
        document.getElementById("hud-follower-cum").textContent = fmt(HUD.followerCum[k], 1);
        document.getElementById("hud-leader-speed").textContent = fmt(HUD.leaderSpeed[k], 2);
        document.getElementById("hud-follower-speed").textContent = fmt(HUD.followerSpeed[k], 2);

        const stateEl = document.getElementById("hud-state");
        stateEl.textContent = HUD.state[k];
        stateEl.style.color = HUD.stateColor[k];
        if (String(HUD.state[k]).includes("ASCEND")) {{
            stateEl.classList.add("ascend-alert");
        }} else {{
            stateEl.classList.remove("ascend-alert");
        }}
    }}

    function updateSpeedLabel(speed) {{
        const label = document.getElementById("speed-label");
        if (!label) return;
        label.textContent = Number(speed).toFixed(2).replace(/0+$/, "").replace(/\\.$/, "");
    }}

    function frameDelayMs(speed) {{
        if (speed <= 0) return null;
        // 1.00x hızlı demo, 0.50x belirgin yavaş, 0.25x yaklaşık gerçek-zamana yakın his verir.
        return 60 + Math.pow(1 - speed, 2) * 1540;
    }}

    window.addEventListener("load", function() {{
        const gd = document.querySelector(".plotly-graph-div");
        if (!gd) return;

        const frameCount = HUD.time.length;
        const speedRange = document.getElementById("speed-range");
        const playBtn = document.getElementById("play-btn");
        const pauseBtn = document.getElementById("pause-btn");
        let currentFrame = 0;
        let playing = false;
        let timer = null;

        function getSpeed() {{
            return speedRange ? Number(speedRange.value) : 0.25;
        }}

        function setButtonState() {{
            if (playBtn) playBtn.classList.toggle("active", playing);
            if (pauseBtn) pauseBtn.classList.toggle("active", !playing);
        }}

        function showFrame(k) {{
            currentFrame = Math.max(0, Math.min(k, frameCount - 1));
            Plotly.animate(gd, [String(currentFrame)], {{
                frame: {{duration: 0, redraw: true}},
                transition: {{duration: 0}},
                mode: "immediate"
            }});
            updateHUD(currentFrame);
        }}

        function stopPlayback() {{
            playing = false;
            if (timer) window.clearTimeout(timer);
            timer = null;
            setButtonState();
        }}

        function tick() {{
            const speed = getSpeed();
            updateSpeedLabel(speed);
            if (!playing || speed <= 0) {{
                stopPlayback();
                return;
            }}
            currentFrame = (currentFrame + 1) % frameCount;
            showFrame(currentFrame);
            timer = window.setTimeout(tick, frameDelayMs(speed));
        }}

        function startPlayback() {{
            const speed = getSpeed();
            updateSpeedLabel(speed);
            if (speed <= 0) {{
                stopPlayback();
                return;
            }}
            if (timer) window.clearTimeout(timer);
            playing = true;
            setButtonState();
            tick();
        }}

        updateHUD(0);
        updateSpeedLabel(getSpeed());
        setButtonState();

        if (playBtn) playBtn.addEventListener("click", startPlayback);
        if (pauseBtn) pauseBtn.addEventListener("click", stopPlayback);
        if (speedRange) {{
            speedRange.addEventListener("input", function() {{
                const speed = getSpeed();
                updateSpeedLabel(speed);
                if (speed <= 0) {{
                    stopPlayback();
                }} else if (playing) {{
                    if (timer) window.clearTimeout(timer);
                    timer = window.setTimeout(tick, frameDelayMs(speed));
                }}
            }});
        }}

        gd.on("plotly_animatingframe", function(e) {{
            let frameName = "0";
            if (e && e.name !== undefined) frameName = e.name;
            else if (e && e.frame && e.frame.name !== undefined) frameName = e.frame.name;
            const k = parseInt(frameName, 10);
            if (Number.isFinite(k)) {{
                currentFrame = Math.max(0, Math.min(k, frameCount - 1));
                updateHUD(currentFrame);
            }}
        }});
    }});
    </script>
    """

    depth_label = "Y / DEPTH" if args.show_negative_depth else "DEPTH |Y|"

    html_template = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="utf-8">
        <title>BlueROV2 Target Tracking - Dynamic Dashboard</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: {PAGE_BG};
                font-family: 'Segoe UI', Arial, sans-serif;
                overflow: hidden;
                color: {TEXT_COLOR};
            }}
            #hud-panel {{
                position: absolute;
                top: 18px;
                left: 18px;
                width: 355px;
                background: {PANEL_BG};
                border: 1px solid {PANEL_BORDER_COLOR};
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.10);
                border-radius: 12px;
                padding: 22px;
                z-index: 1000;
                color: {TEXT_COLOR};
            }}
            .hud-title {{
                color: {TEXT_COLOR};
                font-size: 15px;
                text-transform: uppercase;
                letter-spacing: 1.1px;
                margin: 0 0 14px 0;
                border-bottom: 1px solid {GRID_COLOR};
                padding-bottom: 12px;
            }}
            .stat-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 12px 14px;
            }}
            .stat-box {{ margin-top: 8px; }}
            .stat-box.full {{ grid-column: span 2; }}
            .stat-label {{
                font-size: 10.5px;
                color: {MUTED_TEXT_COLOR};
                text-transform: uppercase;
                letter-spacing: 0.45px;
            }}
            .stat-value {{
                font-size: 20px;
                font-weight: 700;
                color: {TEXT_COLOR};
                margin-top: 3px;
            }}
            .stat-value.small {{ font-size: 16px; }}
            .ascend-alert {{
                color: {ASCEND_COLOR} !important;
                font-weight: 800;
            }}
            .plot-container {{
                width: 100vw;
                height: 100vh;
                position: absolute;
                top: 0;
                left: 0;
                z-index: 1;
            }}
            #summary-panel {{
                position: absolute;
                top: 196px;
                right: 18px;
                width: 310px;
                background: {PANEL_BG};
                border: 1px solid {PANEL_BORDER_COLOR};
                border-radius: 12px;
                padding: 18px;
                z-index: 1000;
                color: {TEXT_COLOR};
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.10);
            }}
            .summary-title {{
                color: {TEXT_COLOR};
                font-size: 13px;
                text-transform: uppercase;
                letter-spacing: 1.1px;
                margin-bottom: 10px;
            }}
            .summary-line {{
                display: flex;
                justify-content: space-between;
                gap: 12px;
                border-bottom: 1px solid {GRID_COLOR};
                padding: 6px 0;
                font-size: 12px;
            }}
            .summary-line span:first-child {{ color: {MUTED_TEXT_COLOR}; }}
            .summary-line span:last-child {{
                color: {TEXT_COLOR};
                font-weight: 600;
            }}
            #playback-panel {{
                position: absolute;
                left: 50%;
                bottom: 18px;
                transform: translateX(-50%);
                width: min(560px, calc(100vw - 40px));
                background: {PANEL_BG};
                border: 1px solid {PANEL_BORDER_COLOR};
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.10);
                border-radius: 14px;
                padding: 12px 16px;
                z-index: 1002;
                color: {TEXT_COLOR};
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .control-button {{
                width: 40px;
                height: 34px;
                border-radius: 10px;
                border: 1px solid {PANEL_BORDER_COLOR};
                background: #ffffff;
                color: {TEXT_COLOR};
                font-size: 15px;
                cursor: pointer;
            }}
            .control-button.active {{
                border-color: {LEADER_COLOR};
                background: #eff6ff;
            }}
            .speed-wrap {{ flex: 1; }}
            .speed-row {{
                display: flex;
                justify-content: space-between;
                font-size: 11px;
                color: {MUTED_TEXT_COLOR};
                margin-bottom: 5px;
                text-transform: uppercase;
                letter-spacing: 0.55px;
            }}
            #speed-range {{
                width: 100%;
                accent-color: {LEADER_COLOR};
                cursor: pointer;
            }}
            .speed-scale {{
                display: flex;
                justify-content: space-between;
                font-size: 10px;
                color: {MUTED_TEXT_COLOR};
                margin-top: 2px;
            }}
        </style>
    </head>
    <body>
        <div id="hud-panel">
            <h2 class="hud-title">BLUEROV2 TARGET TRACKING</h2>
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="stat-label">ANIMATION TIME</div>
                    <div class="stat-value"><span id="hud-time">0.0</span> s</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">SYSTEM STATE</div>
                    <div class="stat-value small" id="hud-state">NOMINAL</div>
                </div>

                <div class="stat-box full">
                    <div class="stat-label">CURRENT VEHICLE SEPARATION</div>
                    <div class="stat-value"><span id="hud-sep3d">0.00</span> m <span style="font-size: 12px; color:#8b949e;">3D</span> / <span id="hud-sepxz">0.00</span> m <span style="font-size: 12px; color:#8b949e;">XZ</span></div>
                </div>

                <div class="stat-box full">
                    <div class="stat-label">FOLLOWER → TARGET ERROR</div>
                    <div class="stat-value"><span id="hud-leak">0.00</span> m</div>
                </div>

                <div class="stat-box full">
                    <div class="stat-label">LEADER / FOLLOWER PATH LENGTH</div>
                    <div class="stat-value small"><span id="hud-leader-cum">0.0</span> m / <span id="hud-follower-cum">0.0</span> m</div>
                </div>

                <div class="stat-box full">
                    <div class="stat-label">LEADER / FOLLOWER {depth_label}</div>
                    <div class="stat-value small"><span id="hud-leader-depth">0.0</span> m / <span id="hud-follower-depth">0.0</span> m</div>
                </div>

                <div class="stat-box full">
                    <div class="stat-label">LEADER / FOLLOWER YAW</div>
                    <div class="stat-value small"><span id="hud-yaw-leader">0.0</span>° / <span id="hud-yaw-follower">0.0</span>°</div>
                </div>

                <div class="stat-box full" style="{'display:none;' if args.hide_speed else ''}">
                    <div class="stat-label">LEADER / FOLLOWER SPEED</div>
                    <div class="stat-value small"><span id="hud-leader-speed">0.00</span> m/s / <span id="hud-follower-speed">0.00</span> m/s</div>
                </div>
            </div>
        </div>

        <div id="summary-panel">
            <div class="summary-title">MISSION SUMMARY</div>
            <div class="summary-line"><span>Sync Duration</span><span>{metrics['sync_duration_s']:.1f} s</span></div>
            <div class="summary-line"><span>Total Path XZ L/T</span><span>{metrics['leader_total_path_xz_m']:.1f} / {metrics['follower_total_path_xz_m']:.1f} m</span></div>
            <div class="summary-line"><span>Mean Leader–Follower Distance</span><span>{metrics['leader_follower_distance_3d']['mean_m']:.2f} m</span></div>
            <div class="summary-line"><span>Max. Leader–Follower Distance</span><span>{metrics['leader_follower_distance_3d']['max_m']:.2f} m</span></div>
            <div class="summary-line"><span>Max. Depth</span><span>{metrics['max_abs_depth_m']:.1f} m</span></div>
            <div class="summary-line"><span>Final Target Error</span><span>{metrics['follower_to_leak_error_xz']['final_m']:.2f} m</span></div>
            <div class="summary-line"><span>Scale</span><span>1U = {args.unity_to_meter:.6f} m</span></div>
        </div>

        <div id="playback-panel">
            <button id="play-btn" class="control-button" title="Play">▶</button>
            <button id="pause-btn" class="control-button active" title="Pause">⏸</button>
            <div class="speed-wrap">
                <div class="speed-row"><span>PLAYBACK SPEED</span><span><span id="speed-label">0.25</span>x</span></div>
                <input id="speed-range" type="range" min="0" max="1" step="0.05" value="0.25">
                <div class="speed-scale"><span>0</span><span>0.25</span><span>0.5</span><span>0.75</span><span>1x</span></div>
            </div>
        </div>

        <div class="plot-container">
            {plot_div}
        </div>
        {hud_script}
    </body>
    </html>
    """

    html_path = out_prefix + "_dashboard.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"[OK] Dinamik dashboard hazır: {html_path}")


def setup_matplotlib_style():
    plt.style.use("default")
    plt.rcParams.update({
        "figure.facecolor": "#ffffff",
        "axes.facecolor": "#ffffff",
        "grid.color": GRID_COLOR,
        "axes.edgecolor": "#9ca3af",
        "text.color": TEXT_COLOR,
        "axes.labelcolor": TEXT_COLOR,
        "xtick.color": "#374151",
        "ytick.color": "#374151",
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "legend.framealpha": 0.95,
        "legend.facecolor": "#ffffff",
        "legend.edgecolor": PANEL_BORDER_COLOR,
    })

def save_static_plots(pl, pf, anim, lab_f, args, out_prefix):
    print("[INFO] Statik PNG grafikler oluşturuluyor...")
    setup_matplotlib_style()

    c_lead_glow, c_lead_core = LEADER_COLOR, LEADER_COLOR
    c_foll_glow, c_foll_core = FOLLOWER_COLOR, FOLLOWER_COLOR
    c_ascend = ASCEND_COLOR

    # 1) Kuşbakışı X-Z navigasyon.
    fig1, ax1 = plt.subplots(figsize=(10, 10))
    ax1.plot(pl["x"], pl["z"], "-", color=c_lead_glow, lw=8, alpha=0.14)
    ax1.plot(pl["x"], pl["z"], "-", color=c_lead_core, lw=1.6, label="Leader Path")
    ax1.plot(pf["x"], pf["z"], "-", color=c_foll_glow, lw=8, alpha=0.14)
    ax1.plot(pf["x"], pf["z"], "-", color=c_foll_core, lw=1.6, label="Follower Path")

    if np.any(lab_f == PHASE_ASCEND):
        ax1.scatter(pf["x"][lab_f == PHASE_ASCEND], pf["z"][lab_f == PHASE_ASCEND],
                    s=72, color=c_ascend, marker="^", edgecolor="white", linewidth=0.7,
                    zorder=5, label="ASCEND")

    ax1.scatter([args.leak_x], [args.leak_z], s=420, color=TARGET_COLOR, marker="*", zorder=6, label="Target")
    ax1.set_title("Autonomous Tracking: Top-Down X-Z Navigation")
    ax1.set_xlabel("X [m]")
    ax1.set_ylabel("Z [m]")
    ax1.grid(True, alpha=0.45)
    ax1.legend(loc="best")
    ax1.set_aspect("equal", adjustable="datalim")
    fig1.tight_layout()
    fig1.savefig(out_prefix + "_1_top_view.png", dpi=300, bbox_inches="tight")
    plt.close(fig1)

    # 2) Derinlik-zaman.
    fig2, ax2 = plt.subplots(figsize=(12, 5))
    d_l = depth_display(anim["yl"], args.show_negative_depth, getattr(args, "depth_display_scale", 1.0))
    d_f = depth_display(anim["yf"], args.show_negative_depth, getattr(args, "depth_display_scale", 1.0))
    ax2.plot(anim["t"], d_l, color=c_lead_core, lw=1.8, label="Leader")
    ax2.plot(anim["t"], d_f, color=c_foll_core, lw=1.8, label="Follower")
    if np.any(anim["phase"] == PHASE_ASCEND):
        ax2.scatter(anim["t"][anim["phase"] == PHASE_ASCEND], d_f[anim["phase"] == PHASE_ASCEND],
                    color=c_ascend, s=18, label="Follower ASCEND", zorder=5)
    ax2.set_title("Depth Profile Over Time")
    ax2.set_xlabel("Time [s]")
    ax2.set_ylabel("Depth [m]" if not args.show_negative_depth else "Y [m]")
    ax2.grid(True, alpha=0.45)
    ax2.legend(loc="best")
    fig2.tight_layout()
    fig2.savefig(out_prefix + "_2_depth_time.png", dpi=300, bbox_inches="tight")
    plt.close(fig2)

    # 3) Lider-takipçi mesafe-zaman.
    fig3, ax3 = plt.subplots(figsize=(12, 5))
    ax3.plot(anim["t"], anim["sep_3d"], lw=1.9, label="3D Distance")
    ax3.plot(anim["t"], anim["sep_xz"], lw=1.9, label="XZ Distance")
    ax3.set_title("Leader–Follower Separation Over Time")
    ax3.set_xlabel("Time [s]")
    ax3.set_ylabel("Distance [m]")
    ax3.grid(True, alpha=0.45)
    ax3.legend(loc="best")
    fig3.tight_layout()
    fig3.savefig(out_prefix + "_3_separation_time.png", dpi=300, bbox_inches="tight")
    plt.close(fig3)

    # 4) Leak hata-zaman.
    fig4, ax4 = plt.subplots(figsize=(12, 5))
    ax4.plot(anim["t"], anim["leak_err"], lw=1.9, label="Follower → Target Error")
    if np.any(anim["phase"] == PHASE_ASCEND):
        ax4.scatter(anim["t"][anim["phase"] == PHASE_ASCEND], anim["leak_err"][anim["phase"] == PHASE_ASCEND],
                    color=c_ascend, s=18, label="ASCEND", zorder=5)
    ax4.set_title("Follower Horizontal Error to Target")
    ax4.set_xlabel("Time [s]")
    ax4.set_ylabel("XZ Error [m]")
    ax4.grid(True, alpha=0.45)
    ax4.legend(loc="best")
    fig4.tight_layout()
    fig4.savefig(out_prefix + "_4_target_error_time.png", dpi=300, bbox_inches="tight")
    plt.close(fig4)

    print(f"[OK] PNG çıktıları: {out_prefix}_1..4_*.png")


def main():
    args = parse_args()
    lp = Path(args.leader)
    fp = Path(args.follower)
    if not lp.exists() or not fp.exists():
        print("[HATA] CSV dosyaları bulunamadı.")
        print(f"  leader  : {lp}")
        print(f"  follower: {fp}")
        return

    # CSV logları Unity birimindedir; analiz/görselleştirme metrede yapılır.
    # Varsayılan olarak leak koordinatları da Unity birimi kabul edilir.
    args.unity_to_meter = float(args.unity_to_meter)
    if args.unity_to_meter <= 0:
        print("[HATA] --unity-to-meter pozitif olmalıdır.")
        return

    raw_leak_x = float(args.leak_x)
    raw_leak_z = float(args.leak_z)
    if not args.leak_coords_meter:
        args.leak_x = raw_leak_x * args.unity_to_meter
        args.leak_z = raw_leak_z * args.unity_to_meter

    pl = read_path(lp, unity_to_meter=args.unity_to_meter)
    pf = read_path(fp, unity_to_meter=args.unity_to_meter)
    if len(pl["x"]) < 2 or len(pf["x"]) < 2:
        print("[HATA] CSV dosyalarında analiz için yeterli geçerli satır yok.")
        return

    args.depth_display_scale, args.raw_max_depth_m = compute_depth_display_scale(pl, pf, args)

    lab_f = classify_phases(
        pf,
        still_speed_eps=args.still_speed_eps,
        ascend_speed_eps=args.ascend_speed_eps,
        min_phase_len=args.min_phase_len,
        latch_ascend=not args.no_ascend_latch,
    )

    out_prefix = args.out[:-4] if args.out.lower().endswith(".png") else args.out

    anim = build_common_animation_data(pl, pf, lab_f, args)
    metrics = make_metrics(pl, pf, anim, lab_f, args)

    write_metrics_json(metrics, out_prefix)
    make_plotly_dashboard(pl, pf, anim, metrics, args, out_prefix)
    save_static_plots(pl, pf, anim, lab_f, args, out_prefix)

    print("\n[ÖZET]")
    print(f"  Senkron süre                 : {metrics['sync_duration_s']:.2f} s")
    print(f"  Lider/Takipçi yol XZ          : {metrics['leader_total_path_xz_m']:.2f} m / {metrics['follower_total_path_xz_m']:.2f} m")
    print(f"  Ortalama takip mesafesi 3D (ASCEND hariç): {metrics['leader_follower_distance_3d']['mean_m']:.2f} m")
    print(f"  Maks. takip mesafesi 3D (ASCEND hariç)   : {metrics['leader_follower_distance_3d']['max_m']:.2f} m")
    print(f"  Final takipçi-leak hatası       : {metrics['follower_to_leak_error_xz']['final_m']:.2f} m")
    print(f"  ASCEND tespiti                  : {metrics['ascend']['detected']} / başlangıç: {metrics['ascend']['start_time_s']}")
    print(f"  ASCEND kilidi                   : {'kapalı' if args.no_ascend_latch else 'açık'}")
    print(f"  Unity→metre katsayısı            : {args.unity_to_meter:.6f} m / Unity unit")
    print(f"  Leak koordinat girdisi           : {'metre' if args.leak_coords_meter else 'Unity unit'}")
    print(f"  HUD hız gösterim ölçeği          : {'gizli' if args.hide_speed else f'x{args.speed_display_scale:.2f}'}")
    print(f"  Uygulanan yaw offsetleri         : lider {args.leader_yaw_offset:+.1f}°, takipçi {args.follower_yaw_offset:+.1f}°")


if __name__ == "__main__":
    main()
