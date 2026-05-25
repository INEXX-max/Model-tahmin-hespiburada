# -*- coding: utf-8 -*-
"""
vehicle_optimization.py
========================
Spot araç optimizasyonu – kiralık araç havuzu + spot araçlar ile talebi
en düşük maliyetle karşılamak için OR-Tools (CP-SAT) ile Tam Sayılı Optimizasyon kullanır.

Çıktı : Arac_Planlama_Yeni.xlsx  (Detay + Özet + Analiz + Filo Kaydırma)
"""

import os
import math
import sys
import warnings
from typing import Optional, Tuple

import pandas as pd
from ortools.sat.python import cp_model
from ortools.constraint_solver import routing_enums_pb2, pywrapcp

warnings.filterwarnings("ignore", category=UserWarning)


def _safe_text(value: str) -> str:
    """Stdout encodingine uygun, yazdırılabilir metin döndürür."""
    encoding = sys.stdout.encoding or "utf-8"
    try:
        return str(value).encode(encoding, "replace").decode(encoding)
    except Exception:
        return str(value).encode("utf-8", "replace").decode("utf-8")


def _safe_print(text: str) -> None:
    """Unicode kaynaklı konsol hatalarını engelleyen print."""
    print(_safe_text(text))

# ──────────────────────────────────────────────────────────────────────
# Yardımcı: Dosya adını kısmi eşleşmeyle bul (Türkçe encoding sorunları)
# ──────────────────────────────────────────────────────────────────────

def _find_file(directory: str, partial_name: str) -> str:
    """
    *directory* içinde *partial_name* alt-dizesini (büyük/küçük harf duyarsız)
    içeren ilk dosyayı döndürür. Bulamazsa FileNotFoundError fırlatır.
    """
    partial_lower = partial_name.lower()
    for fname in os.listdir(directory):
        if partial_lower in fname.lower():
            return os.path.join(directory, fname)
    raise FileNotFoundError(
        f"'{partial_name}' içeren dosya bulunamadı: {directory}"
    )


# ──────────────────────────────────────────────────────────────────────
# Haversine mesafe hesabı
# ──────────────────────────────────────────────────────────────────────

_R_KM = 6371.0          # Dünya yarıçapı (km)
_ROAD_FACTOR = 1.3       # Karayolu düzeltme çarpanı


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """İki koordinat arası Haversine mesafesi (km), yol faktörü ile çarpılmış."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return _R_KM * c * _ROAD_FACTOR


# ──────────────────────────────────────────────────────────────────────
# Mesafe matrisi oluştur
# ──────────────────────────────────────────────────────────────────────

def build_distance_map(coord_df: pd.DataFrame) -> dict:
    """
    Koordinatlar tablosundan (Transfer Merkezi, Enlem, Boylam)
    {(çıkış, varış): mesafe_km} sözlüğü üretir.
    """
    dist_map: dict = {}
    centers = coord_df["Transfer Merkezi"].tolist()
    lats = coord_df["Enlem"].tolist()
    lons = coord_df["Boylam"].tolist()
    for i, c1 in enumerate(centers):
        for j, c2 in enumerate(centers):
            if i != j:
                dist_map[(c1, c2)] = haversine_km(lats[i], lons[i], lats[j], lons[j])
    return dist_map


# ──────────────────────────────────────────────────────────────────────
# Araç verisi
# ──────────────────────────────────────────────────────────────────────

# Sıralama: Tır, Kamyon, Hafif Kamyon, Kamyonet
VEHICLE_NAMES = ["Tır", "Kamyon", "Hafif Kamyon", "Kamyonet"]

# Varsayılan değerler (dosya okunamazsa kullanılır)
_DEFAULT_CAPACITY     = [22_400, 12_000, 7_200, 5_600]
_DEFAULT_KIRALIK_DAILY = [7_000, 5_000, 5_000, 3_750]
_DEFAULT_KIRALIK_KM    = [13, 10, 10, 6]
_DEFAULT_SPOT_DAILY    = [11_700, 7_638, 8_750, 4_750]
_DEFAULT_SPOT_KM       = [25, 21, 20, 18]


def _match_vehicle_name(name: str) -> Optional[str]:
    """Araç adını kanonik isimlerle eşleştirir (Tır, Kamyon, Hafif Kamyon, Kamyonet)."""
    name = str(name).strip()
    if not name:
        return None
    lower = name.lower()
    for vn in VEHICLE_NAMES:
        vnl = vn.lower()
        if vnl in lower or lower in vnl:
            return vn
    return None


def _load_vehicle_params(base_dir: str) -> dict:
    """Araç_Kapasite_Maliyet.xlsx dosyasından araç parametrelerini yükler."""
    params: dict = {
        "capacity": dict(zip(VEHICLE_NAMES, _DEFAULT_CAPACITY)),
        "kiralik_daily": dict(zip(VEHICLE_NAMES, _DEFAULT_KIRALIK_DAILY)),
        "kiralik_km": dict(zip(VEHICLE_NAMES, _DEFAULT_KIRALIK_KM)),
        "spot_daily": dict(zip(VEHICLE_NAMES, _DEFAULT_SPOT_DAILY)),
        "spot_km": dict(zip(VEHICLE_NAMES, _DEFAULT_SPOT_KM)),
    }
    try:
        path = _find_file(base_dir, "Kapasite_Maliyet")
        df = pd.read_excel(path)
        # Sütun isimlerini normalize et
        col_map = {}
        for c in df.columns:
            cl = c.lower()
            if "adı" in cl or "ad" in cl:
                col_map["name"] = c
            elif "kapasite" in cl:
                col_map["cap"] = c
            elif "kiralık" in cl and "günlük" in cl:
                col_map["k_daily"] = c
            elif "kiralık" in cl and "kilometre" in cl:
                col_map["k_km"] = c
            elif "spot" in cl and ("sabit" in cl or "günlük" in cl):
                col_map["s_daily"] = c
            elif "spot" in cl and "kilometre" in cl:
                col_map["s_km"] = c

        for _, row in df.iterrows():
            name = str(row.get(col_map.get("name", ""), "")).strip()
            matched = _match_vehicle_name(name)
            if not matched:
                continue
            if "cap" in col_map:
                val = row[col_map["cap"]]
                if pd.notna(val):
                    params["capacity"][matched] = float(str(val).replace(".", "").replace(",", "."))
            if "k_daily" in col_map:
                val = row[col_map["k_daily"]]
                if pd.notna(val):
                    params["kiralik_daily"][matched] = float(str(val).replace(".", "").replace(",", "."))
            if "k_km" in col_map:
                val = row[col_map["k_km"]]
                if pd.notna(val):
                    params["kiralik_km"][matched] = float(str(val).replace(".", "").replace(",", "."))
            if "s_daily" in col_map:
                val = row[col_map["s_daily"]]
                if pd.notna(val):
                    params["spot_daily"][matched] = float(str(val).replace(".", "").replace(",", "."))
            if "s_km" in col_map:
                val = row[col_map["s_km"]]
                if pd.notna(val):
                    params["spot_km"][matched] = float(str(val).replace(".", "").replace(",", "."))
        _safe_print("[OK] Araç parametreleri dosyadan yüklendi.")
    except FileNotFoundError:
        _safe_print("[!] Araç_Kapasite_Maliyet dosyası bulunamadı - varsayılan değerler kullaniliyor.")
    return params


# ──────────────────────────────────────────────────────────────────────
# Kiralık araç verisi
# ──────────────────────────────────────────────────────────────────────

def _load_rental_vehicles(base_dir: str) -> pd.DataFrame:
    """
    Kiralık_Araçlar.xlsx → DataFrame
    Sütunlar: Çıkış Transfer Merkezi, Varış Transfer Merkezi, Araç sayısı, Araç Türü
    """
    try:
        path = _find_file(base_dir, "Arac")
        # "Kiralık" veya "Kiralik" içeren dosyayı tercih et
        try:
            path = _find_file(base_dir, "Kiral")
        except FileNotFoundError:
            pass
        df = pd.read_excel(path)
        _safe_print(f"[OK] Kiralik arac dosyasi yuklendi: {os.path.basename(path)}")
        return df
    except FileNotFoundError:
        _safe_print("[!] Kiralik arac dosyasi bulunamadi - varsayilan tablo kullaniliyor.")
        # Varsayılan kiralık araç tablosu
        records = [
            ("İstanbul", "Yalova", 2, "Tır"),
            ("İstanbul", "Eskişehir", 2, "Tır"),
            ("İstanbul", "Manisa", 1, "Tır"),
            ("İstanbul", "Balıkesir", 1, "Tır"),
            ("İstanbul", "Tekirdağ", 1, "Tır"),
            ("Kocaeli", "İstanbul", 1, "Tır"),
            ("Kocaeli", "Tekirdağ", 1, "Tır"),
            ("Kocaeli", "Balıkesir", 1, "Kamyon"),
            ("Kocaeli", "Eskişehir", 1, "Kamyon"),
            ("Yalova", "Eskişehir", 1, "Kamyon"),
            ("Yalova", "Tekirdağ", 1, "Kamyon"),
        ]
        return pd.DataFrame(records, columns=[
            "Çıkış Transfer Merkezi", "Varış Transfer Merkezi",
            "Araç sayısı", "Araç Türü"
        ])


def _build_rental_lookup(rental_df: pd.DataFrame) -> dict:
    """
    {(çıkış, varış): [(araç_türü, adet), ...]} sözlüğü oluşturur.
    """
    lookup: dict = {}
    # Sütun isimlerini belirle
    cols = rental_df.columns.tolist()
    col_cikis = cols[0]
    col_varis = cols[1]
    col_adet = cols[2]
    col_tur = cols[3]

    for _, row in rental_df.iterrows():
        key = (str(row[col_cikis]).strip(), str(row[col_varis]).strip())
        adet_val = pd.to_numeric(row[col_adet], errors="coerce")
        adet = int(adet_val) if pd.notna(adet_val) else 0
        tur = _match_vehicle_name(row[col_tur])
        if not tur or adet <= 0:
            continue
        lookup.setdefault(key, []).append((tur, adet))
    return lookup


def _standardize_forecast_columns(forecast_df: pd.DataFrame) -> pd.DataFrame:
    """Tahmin verisini standart kolonlara dönüştürür."""
    fcols = forecast_df.columns.tolist()
    if len(fcols) < 4:
        raise ValueError("Tahmin dosyasında beklenen en az 4 sütun bulunamadı.")

    df = forecast_df.rename(
        columns={
            fcols[0]: "Cikis",
            fcols[1]: "Varis",
            fcols[2]: "Tarih",
            fcols[3]: "Talep",
        }
    ).copy()

    df["Cikis"] = df["Cikis"].astype(str).str.strip()
    df["Varis"] = df["Varis"].astype(str).str.strip()
    df["Tarih"] = pd.to_datetime(df["Tarih"])
    df["Talep"] = pd.to_numeric(df["Talep"], errors="coerce").fillna(0.0)
    return df


def _summarize_routes_by_demand(forecast_df: pd.DataFrame) -> pd.DataFrame:
    """Güzergahlari toplam talebe göre sıralar."""
    return (
        forecast_df
        .groupby(["Cikis", "Varis"], as_index=False)["Talep"]
        .sum()
        .rename(columns={"Talep": "Toplam Talep Desi"})
        .sort_values("Toplam Talep Desi", ascending=False)
    )


def _summarize_routes_by_cost(planning_df: pd.DataFrame) -> pd.DataFrame:
    """Güzergahlari toplam maliyete göre sıralar."""
    return (
        planning_df
        .groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"], as_index=False)
        .agg({
            "Toplam Maliyet (TL)": "sum",
            "Kiralık Maliyet (TL)": "sum",
            "Spot Maliyet (TL)": "sum",
        })
        .sort_values("Toplam Maliyet (TL)", ascending=False)
    )


def _build_rental_pool(rental_lookup: dict) -> Tuple[dict, dict]:
    """Kiralık araç havuzunu ve başlangıç rota dağılımını çıkarır."""
    pool = {v: 0 for v in VEHICLE_NAMES}
    initial_by_route = {}
    for route, items in rental_lookup.items():
        route_counts = {v: 0 for v in VEHICLE_NAMES}
        for tur, adet in items:
            if tur not in VEHICLE_NAMES:
                continue
            pool[tur] += adet
            route_counts[tur] += adet
        initial_by_route[route] = route_counts
    return pool, initial_by_route


def _filter_forecast_by_cities(
    forecast_df: pd.DataFrame,
    city_set: set,
) -> Tuple[pd.DataFrame, int]:
    """Koordinatlar listesinde olmayan şehirleri filtreler."""
    mask = forecast_df["Cikis"].isin(city_set) & forecast_df["Varis"].isin(city_set)
    excluded = int((~mask).sum())
    return forecast_df.loc[mask].copy(), excluded


def _split_demand_chunks(demand: float, max_cap: float) -> list:
    """Talebi max kapasiteye göre parçalara ayırır."""
    chunks = []
    remaining = float(demand)
    while remaining > 0:
        chunk = min(max_cap, remaining)
        chunks.append(chunk)
        remaining -= chunk
    return chunks


def _min_load_by_type(params: dict) -> dict:
    """Araç tipine göre minimum yük kısıtı tanımlar."""
    caps = params["capacity"]
    return {
        "Kamyonet": 0.0,
        "Hafif Kamyon": caps["Kamyonet"] + 1.0,
        "Kamyon": caps["Hafif Kamyon"] + 1.0,
        "Tır": caps["Kamyon"] + 1.0,
    }


def _estimate_origin_avg_distance(day_df: pd.DataFrame, dist_map: dict) -> dict:
    """Origin bazında ağırlıklı ortalama mesafe hesaplar."""
    totals = {}
    weights = {}
    for _, row in day_df.iterrows():
        origin = row["Cikis"]
        dest = row["Varis"]
        demand = float(row["Talep"])
        if demand <= 0:
            continue
        dist = dist_map.get((origin, dest), 0.0)
        totals[origin] = totals.get(origin, 0.0) + dist * demand
        weights[origin] = weights.get(origin, 0.0) + demand
    avg = {}
    for origin, total in totals.items():
        w = weights.get(origin, 0.0)
        avg[origin] = (total / w) if w > 0 else 0.0
    return avg


def _allocate_rental_pool_to_origins(
    day_df: pd.DataFrame,
    dist_map: dict,
    params: dict,
    rental_pool: dict,
) -> Tuple[dict, dict]:
    """Kiralık araç havuzunu origin bazında yeniden dağıtır (CP-SAT)."""
    origin_totals = (
        day_df.groupby("Cikis", as_index=False)["Talep"].sum().set_index("Cikis")["Talep"].to_dict()
    )
    avg_dist = _estimate_origin_avg_distance(day_df, dist_map)
    min_loads = _min_load_by_type(params)

    required_counts = {}
    for origin, total_demand in origin_totals.items():
        required_counts[origin] = {}
        for v in VEHICLE_NAMES:
            if total_demand < min_loads[v]:
                required_counts[origin][v] = 0
                continue
            cap = params["capacity"][v]
            count_by_demand = int(math.ceil(total_demand / cap)) if total_demand > 0 else 0
            required_counts[origin][v] = count_by_demand

    model = cp_model.CpModel()
    alloc_vars = {}
    cost_scale = 100

    for origin, type_counts in required_counts.items():
        for v in VEHICLE_NAMES:
            ub = type_counts.get(v, 0)
            alloc_vars[(origin, v)] = model.NewIntVar(0, ub, f"alloc_{origin}_{v}")

    for v in VEHICLE_NAMES:
        model.Add(
            sum(alloc_vars[(origin, v)] for origin in required_counts.keys())
            <= rental_pool.get(v, 0)
        )

    objective_terms = []
    for origin, type_counts in required_counts.items():
        dist = avg_dist.get(origin, 0.0)
        for v in VEHICLE_NAMES:
            rental_cost = params["kiralik_daily"][v] + dist * params["kiralik_km"][v]
            spot_cost = params["spot_daily"][v] + dist * params["spot_km"][v]

            savings = max(0.0, spot_cost - rental_cost)
            if savings > 0:
                objective_terms.append(int(round(savings * cost_scale)) * alloc_vars[(origin, v)])

    if objective_terms:
        model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("CP-SAT kiralik havuz dagitimi bulunamadi.")

    allocation = {origin: {v: 0 for v in VEHICLE_NAMES} for origin in required_counts.keys()}
    for origin in required_counts.keys():
        for v in VEHICLE_NAMES:
            allocation[origin][v] = int(solver.Value(alloc_vars[(origin, v)]))

    return allocation, required_counts


def _build_nodes_for_origin(
    day_df: pd.DataFrame,
    origin: str,
    params: dict,
) -> list:
    """Origin bazında node listesi oluşturur."""
    nodes = []
    max_cap = max(params["capacity"].values())
    for _, row in day_df.iterrows():
        if row["Cikis"] != origin:
            continue
        dest = row["Varis"]
        demand = float(row["Talep"])
        if demand <= 0:
            continue
        for chunk_demand in _split_demand_chunks(demand, max_cap):
            nodes.append({
                "city": dest,
                "demand": float(chunk_demand),
                "route_key": (origin, dest),
            })
    return nodes


def _solve_routing_for_origin(
    day,
    origin: str,
    nodes: list,
    vehicles: list,
    dist_map: dict,
    params: dict,
) -> Tuple[list, list, dict]:
    """Routing API ile multi-drop rota optimizasyonu."""
    if not nodes or not vehicles:
        return [], [], {}

    def distance_between(c1: str, c2: str) -> float:
        if c1 == c2:
            return 0.0
        return dist_map.get((c1, c2), 0.0)

    # Node list: depot + nodes
    index_to_node = [
        {"city": origin, "demand": 0.0, "route_key": None}
    ] + nodes

    manager = pywrapcp.RoutingIndexManager(len(index_to_node), len(vehicles), 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_km(from_index, to_index):
        from_node = index_to_node[manager.IndexToNode(from_index)]["city"]
        to_node = index_to_node[manager.IndexToNode(to_index)]["city"]
        return distance_between(from_node, to_node)

    cost_callback_indices = []
    for vehicle in vehicles:
        cost_per_km = vehicle["cost_per_km"]

        def make_callback(veh, cpk):
            def _cost_callback(from_index, to_index):
                dist = distance_km(from_index, to_index)
                cost = dist * cpk * 100
                
                return int(round(cost))
            return _cost_callback

        callback_index = routing.RegisterTransitCallback(make_callback(vehicle, cost_per_km))
        cost_callback_indices.append(callback_index)

    for vid, callback_index in enumerate(cost_callback_indices):
        routing.SetArcCostEvaluatorOfVehicle(callback_index, vid)

    def demand_callback(from_index):
        node = index_to_node[manager.IndexToNode(from_index)]
        return int(round(node["demand"] * 100))

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)

    capacities = [int(round(v["capacity"] * 100)) for v in vehicles]
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        capacities,
        True,
        "Capacity",
    )

    capacity_dim = routing.GetDimensionOrDie("Capacity")
    min_loads = _min_load_by_type(params)

    # Her node icin kapasiteye gore izinli araclar
    for node_idx in range(1, len(index_to_node)):
        node_demand = index_to_node[node_idx]["demand"]
        allowed = [
            vid for vid, vehicle in enumerate(vehicles)
            if vehicle["capacity"] >= node_demand
        ]
        if allowed:
            routing.VehicleVar(manager.NodeToIndex(node_idx)).SetValues(allowed)

    # Arac tipi bazli minimum yuk kısıti CP-SAT kisminda yapildigi icin Routing modeline eklenmiyor.
    # Bu kisim aracin bos kalmasi durumunda 'CP Solver fail' hatasina yol aciyordu.

    for vid, vehicle in enumerate(vehicles):
        routing.SetFixedCostOfVehicle(int(round(vehicle["fixed_cost"] * 100)), vid)

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_params.time_limit.FromSeconds(1)

    solution = routing.SolveWithParameters(search_params)
    if solution is None:
        return _fallback_routing(day, origin, nodes, vehicles, dist_map)

    multi_drop_rows = []
    route_assignments = []
    route_vehicle_counts = {}

    for vid, vehicle in enumerate(vehicles):
        index = routing.Start(vid)
        route_nodes = []
        route_city_seq = [origin]
        route_distance = 0.0
        route_demand = 0.0

        while not routing.IsEnd(index):
            next_index = solution.Value(routing.NextVar(index))
            from_node = index_to_node[manager.IndexToNode(index)]
            to_node = index_to_node[manager.IndexToNode(next_index)]
            route_distance += distance_km(index, next_index)
            if manager.IndexToNode(next_index) != 0:
                route_nodes.append(manager.IndexToNode(next_index))
                route_city_seq.append(to_node["city"])
                route_demand += to_node["demand"]
            index = next_index

        if not route_nodes:
            continue

        route_city_seq.append(origin)
        fixed_cost = vehicle["fixed_cost"]
        cost_per_km = vehicle["cost_per_km"]
        route_cost = fixed_cost + route_distance * cost_per_km

        stop_parts = []
        for node_idx in route_nodes:
            node = index_to_node[node_idx]
            stop_parts.append(f"{node['city']}: {node['demand']:.0f}")

        drop_count = len(route_nodes)
        delivery_type = "Dogrudan" if drop_count == 1 else "Multi-Drop"

        multi_drop_rows.append({
            "Tarih": day,
            "Arac Tipi": vehicle["type"],
            "Arac Kategorisi": vehicle["category"],
            "Baslangic": origin,
            "Rota": " -> ".join(route_city_seq),
            "Durak Detay": "; ".join(stop_parts),
            "Durak Sayisi": drop_count,
            "Teslimat Tipi": delivery_type,
            "Toplam Tasinan Desi": round(route_demand, 2),
            "Toplam Mesafe (km)": round(route_distance, 2),
            "Toplam Maliyet (TL)": round(route_cost, 2),
        })

        visited_routes = set()
        for node_idx in route_nodes:
            node = index_to_node[node_idx]
            route_key = node["route_key"]
            route_assignments.append({
                "route_key": route_key,
                "demand": node["demand"],
                "vehicle": vehicle,
                "route_cost": route_cost,
                "route_demand": route_demand,
            })
            if route_key not in visited_routes:
                route_vehicle_counts.setdefault(route_key, {"Kiralik": {v: 0 for v in VEHICLE_NAMES},
                                                           "Spot": {v: 0 for v in VEHICLE_NAMES}})
                route_vehicle_counts[route_key][vehicle["category"]][vehicle["type"]] += 1
                visited_routes.add(route_key)

    return route_assignments, multi_drop_rows, route_vehicle_counts


def _fallback_routing(
    day,
    origin: str,
    nodes: list,
    vehicles: list,
    dist_map: dict,
) -> Tuple[list, list, dict]:
    """Routing başarısız olursa basit greedy multi-drop fallback uygular."""
    if not nodes or not vehicles:
        return [], [], {}

    def distance_between(c1: str, c2: str) -> float:
        if c1 == c2:
            return 0.0
        return dist_map.get((c1, c2), 0.0)

    route_assignments = []
    multi_drop_rows = []
    route_vehicle_counts = {}

    node_list = sorted(nodes, key=lambda n: n["demand"], reverse=True)
    vehicle_list = sorted(vehicles, key=lambda v: v["capacity"])

    for vehicle in vehicle_list:
        capacity = float(vehicle["capacity"])
        route_nodes = []
        load = 0.0

        i = 0
        while i < len(node_list):
            node = node_list[i]
            if load + node["demand"] <= capacity:
                route_nodes.append(node)
                load += node["demand"]
                node_list.pop(i)
            else:
                i += 1

        if not route_nodes:
            continue

        route_city_seq = [origin] + [n["city"] for n in route_nodes] + [origin]
        route_distance = 0.0
        for c1, c2 in zip(route_city_seq, route_city_seq[1:]):
            route_distance += distance_between(c1, c2)

        route_demand = sum(n["demand"] for n in route_nodes)
        route_cost = vehicle["fixed_cost"] + route_distance * vehicle["cost_per_km"]

        stop_parts = [f"{n['city']}: {n['demand']:.0f}" for n in route_nodes]
        drop_count = len(route_nodes)
        delivery_type = "Dogrudan" if drop_count == 1 else "Multi-Drop"

        multi_drop_rows.append({
            "Tarih": day,
            "Arac Tipi": vehicle["type"],
            "Arac Kategorisi": vehicle["category"],
            "Baslangic": origin,
            "Rota": " -> ".join(route_city_seq),
            "Durak Detay": "; ".join(stop_parts),
            "Durak Sayisi": drop_count,
            "Teslimat Tipi": delivery_type,
            "Toplam Tasinan Desi": round(route_demand, 2),
            "Toplam Mesafe (km)": round(route_distance, 2),
            "Toplam Maliyet (TL)": round(route_cost, 2),
        })

        visited_routes = set()
        for node in route_nodes:
            route_key = node["route_key"]
            route_assignments.append({
                "route_key": route_key,
                "demand": node["demand"],
                "vehicle": vehicle,
                "route_cost": route_cost,
                "route_demand": route_demand,
            })
            if route_key not in visited_routes:
                route_vehicle_counts.setdefault(route_key, {
                    "Kiralik": {vt: 0 for vt in VEHICLE_NAMES},
                    "Spot": {vt: 0 for vt in VEHICLE_NAMES},
                })
                route_vehicle_counts[route_key][vehicle["category"]][vehicle["type"]] += 1
                visited_routes.add(route_key)

    return route_assignments, multi_drop_rows, route_vehicle_counts


def _run_baseline_planning(
    forecast_df: pd.DataFrame,
    dist_map: dict,
    params: dict,
    rental_lookup: dict,
) -> pd.DataFrame:
    """Kiralık araçların sabit kabul edildiği eski optimizasyonu çalıştırır."""
    results = []

    for _, row in forecast_df.iterrows():
        cikis = row["Cikis"]
        varis = row["Varis"]
        tarih = row["Tarih"]
        talep_desi = float(row["Talep"])

        dist_km = dist_map.get((cikis, varis), 0.0)
        kiralik_list = rental_lookup.get((cikis, varis), [])

        kiralik_counts = {v: 0 for v in VEHICLE_NAMES}
        kiralik_cap = 0.0
        kiralik_cost_route = 0.0

        for tur, adet in kiralik_list:
            cap_per = params["capacity"].get(tur, 0)
            daily = params["kiralik_daily"].get(tur, 0)
            km_cost = params["kiralik_km"].get(tur, 0)
            cost = adet * (daily + dist_km * km_cost)
            kiralik_cost_route += cost
            kiralik_cap += adet * cap_per
            kiralik_counts[tur] += adet

        remaining = max(0.0, talep_desi - kiralik_cap)

        spot_counts = {v: 0 for v in VEHICLE_NAMES}
        spot_cost_route = 0.0

        if remaining > 0:
            spot_counts = _solve_spot_ilp(remaining, dist_km, params)
            for v in VEHICLE_NAMES:
                cnt = spot_counts.get(v, 0)
                if cnt > 0:
                    spot_cost_route += cnt * (
                        params["spot_daily"][v] + dist_km * params["spot_km"][v]
                    )

        toplam = kiralik_cost_route + spot_cost_route

        kiralik_adet = sum(kiralik_counts.values())
        spot_detail = "; ".join([f"{v}: {spot_counts.get(v, 0)}" for v in VEHICLE_NAMES])

        results.append({
            "Tarih": tarih,
            "Çıkış Transfer Merkezi": cikis,
            "Varış Transfer Merkezi": varis,
            "Taşınan Desi": round(talep_desi, 2),
            "Mesafe (km)": round(dist_km, 2),
            "Kiralık Araç Sayısı": int(kiralik_adet),
            "Spot Araçlar": spot_detail,
            "Kiralık Tır": kiralik_counts.get("Tır", 0),
            "Kiralık Kamyon": kiralik_counts.get("Kamyon", 0),
            "Kiralık Hafif Kamyon": kiralik_counts.get("Hafif Kamyon", 0),
            "Kiralık Kamyonet": kiralik_counts.get("Kamyonet", 0),
            "Spot Tır": spot_counts.get("Tır", 0),
            "Spot Kamyon": spot_counts.get("Kamyon", 0),
            "Spot Hafif Kamyon": spot_counts.get("Hafif Kamyon", 0),
            "Spot Kamyonet": spot_counts.get("Kamyonet", 0),
            "Kiralık Maliyet (TL)": round(kiralik_cost_route, 2),
            "Spot Maliyet (TL)": round(spot_cost_route, 2),
            "Toplam Maliyet (TL)": round(toplam, 2),
        })

    return pd.DataFrame(results)


def _route_label(route_key: Tuple[str, str]) -> str:
    return f"{route_key[0]} -> {route_key[1]}"


def _build_move_summary(
    day,
    initial_by_route: dict,
    final_by_route: dict,
    route_demand_map: dict,
) -> pd.DataFrame:
    """Kaydırılan kiralık araçların özetini üretir."""
    moves = []
    all_routes = set(initial_by_route.keys()) | set(final_by_route.keys())

    for v in VEHICLE_NAMES:
        releases = []
        receives = []

        for route in all_routes:
            init_cnt = initial_by_route.get(route, {}).get(v, 0)
            final_cnt = final_by_route.get(route, {}).get(v, 0)
            delta = final_cnt - init_cnt
            if delta < 0:
                releases.append([route, -delta])
            elif delta > 0:
                receives.append([route, delta])

        i = 0
        j = 0
        while i < len(releases) and j < len(receives):
            from_route, from_qty = releases[i]
            to_route, to_qty = receives[j]
            qty = min(from_qty, to_qty)

            moves.append({
                "Tarih": day,
                "Araç Türü": v,
                "Kaynak Güzergah": _route_label(from_route),
                "Hedef Güzergah": _route_label(to_route),
                "Adet": qty,
                "Kaynak Talep (Desi)": route_demand_map.get(from_route, 0.0),
                "Hedef Talep (Desi)": route_demand_map.get(to_route, 0.0),
            })

            releases[i][1] -= qty
            receives[j][1] -= qty

            if releases[i][1] == 0:
                i += 1
            if receives[j][1] == 0:
                j += 1

        # Kalan araçlar boştadır
        for k in range(i, len(releases)):
            route, qty_left = releases[k]
            if qty_left <= 0:
                continue
            moves.append({
                "Tarih": day,
                "Araç Türü": v,
                "Kaynak Güzergah": _route_label(route),
                "Hedef Güzergah": "BOŞTA",
                "Adet": qty_left,
                "Kaynak Talep (Desi)": route_demand_map.get(route, 0.0),
                "Hedef Talep (Desi)": 0.0,
            })

    return pd.DataFrame(moves)


def _optimize_with_fleet_pool(
    forecast_df: pd.DataFrame,
    dist_map: dict,
    params: dict,
    rental_pool: dict,
    initial_by_route: dict,
    route_demand_map: dict,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Kiralık araç havuzunu rota bazında yeniden dağıtarak optimizasyon yapar."""
    results = []
    move_rows = []

    caps = {v: params["capacity"][v] for v in VEHICLE_NAMES}

    for day, day_df in forecast_df.groupby("Tarih"):
        day_routes = (
            day_df
            .groupby(["Cikis", "Varis"], as_index=False)["Talep"]
            .sum()
        )
        day_demand = {
            (r["Cikis"], r["Varis"]): float(r["Talep"])
            for _, r in day_routes.iterrows()
        }

        route_keys = set(day_demand.keys()) | set(initial_by_route.keys())
        routes = []
        for key in route_keys:
            routes.append({
                "key": key,
                "demand": day_demand.get(key, 0.0),
                "distance": dist_map.get(key, 0.0),
            })

        # CP-SAT model
        model = cp_model.CpModel()
        cap_scale = 100
        cost_scale = 100
        scaled_caps = {v: int(round(caps[v] * cap_scale)) for v in VEHICLE_NAMES}

        rental_vars = {}
        spot_vars = {}

        for r_idx, r in enumerate(routes):
            scaled_demand = int(math.ceil(r["demand"] * cap_scale))
            for v in VEHICLE_NAMES:
                cap_v = scaled_caps[v]
                if scaled_demand <= 0:
                    ub = 0
                else:
                    ub = max(1, math.ceil(scaled_demand / cap_v) + 1)

                rental_vars[(r_idx, v)] = model.NewIntVar(0, ub, f"rent_{r_idx}_{v}")
                spot_vars[(r_idx, v)] = model.NewIntVar(0, ub, f"spot_{r_idx}_{v}")

            # Talep kısıtı: kapasite >= demand
            model.Add(
                sum(
                    scaled_caps[v] * (rental_vars[(r_idx, v)] + spot_vars[(r_idx, v)])
                    for v in VEHICLE_NAMES
                ) >= scaled_demand
            )

        # Kiralık araç havuz kısıtları
        for v in VEHICLE_NAMES:
            model.Add(
                sum(rental_vars[(r_idx, v)] for r_idx in range(len(routes))) <= rental_pool.get(v, 0)
            )

        # Amaç fonksiyonu
        objective_terms = []
        for r_idx, r in enumerate(routes):
            dist = r["distance"]
            for v in VEHICLE_NAMES:
                rental_cost = params["kiralik_daily"][v] + dist * params["kiralik_km"][v]
                spot_cost = params["spot_daily"][v] + dist * params["spot_km"][v]
                objective_terms.append(int(round(rental_cost * cost_scale)) * rental_vars[(r_idx, v)])
                objective_terms.append(int(round(spot_cost * cost_scale)) * spot_vars[(r_idx, v)])
        model.Minimize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        solver.parameters.num_search_workers = 8

        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError("CP-SAT çözümü bulunamadı. Model parametrelerini kontrol edin.")

        final_by_route = {}

        for r_idx, r in enumerate(routes):
            route_key = r["key"]
            cikis, varis = route_key
            talep_desi = r["demand"]
            dist_km = r["distance"]

            rental_counts = {v: int(solver.Value(rental_vars[(r_idx, v)])) for v in VEHICLE_NAMES}
            spot_counts = {v: int(solver.Value(spot_vars[(r_idx, v)])) for v in VEHICLE_NAMES}
            final_by_route[route_key] = rental_counts

            kiralik_cost_route = 0.0
            spot_cost_route = 0.0
            for v in VEHICLE_NAMES:
                if rental_counts[v] > 0:
                    kiralik_cost_route += rental_counts[v] * (
                        params["kiralik_daily"][v] + dist_km * params["kiralik_km"][v]
                    )
                if spot_counts[v] > 0:
                    spot_cost_route += spot_counts[v] * (
                        params["spot_daily"][v] + dist_km * params["spot_km"][v]
                    )

            toplam = kiralik_cost_route + spot_cost_route
            kiralik_adet = sum(rental_counts.values())
            spot_detail = "; ".join([f"{v}: {spot_counts.get(v, 0)}" for v in VEHICLE_NAMES])

            results.append({
                "Tarih": day,
                "Çıkış Transfer Merkezi": cikis,
                "Varış Transfer Merkezi": varis,
                "Taşınan Desi": round(talep_desi, 2),
                "Mesafe (km)": round(dist_km, 2),
                "Kiralık Araç Sayısı": int(kiralik_adet),
                "Spot Araçlar": spot_detail,
                "Kiralık Tır": rental_counts.get("Tır", 0),
                "Kiralık Kamyon": rental_counts.get("Kamyon", 0),
                "Kiralık Hafif Kamyon": rental_counts.get("Hafif Kamyon", 0),
                "Kiralık Kamyonet": rental_counts.get("Kamyonet", 0),
                "Spot Tır": spot_counts.get("Tır", 0),
                "Spot Kamyon": spot_counts.get("Kamyon", 0),
                "Spot Hafif Kamyon": spot_counts.get("Hafif Kamyon", 0),
                "Spot Kamyonet": spot_counts.get("Kamyonet", 0),
                "Kiralık Maliyet (TL)": round(kiralik_cost_route, 2),
                "Spot Maliyet (TL)": round(spot_cost_route, 2),
                "Toplam Maliyet (TL)": round(toplam, 2),
            })

        move_df = _build_move_summary(day, initial_by_route, final_by_route, route_demand_map)
        if not move_df.empty:
            move_rows.append(move_df)

    planning_df = pd.DataFrame(results)
    move_df = pd.concat(move_rows, ignore_index=True) if move_rows else pd.DataFrame()
    return planning_df, move_df


# ──────────────────────────────────────────────────────────────────────
# ILP ile Spot Araç Optimizasyonu
# ──────────────────────────────────────────────────────────────────────

def _solve_spot_ilp(
    remaining_desi: float,
    distance_km: float,
    params: dict,
) -> dict:
    """
    Kalan talebi karşılamak için en düşük maliyetli spot araç kombinasyonunu bulur.

    Karar değişkenleri : n_tır, n_kamyon, n_hafif_kamyon, n_kamyonet  (tamsayı ≥ 0)
    Amaç              : min Σ n_i × (spot_günlük_i + mesafe × spot_km_i)
    Kısıt             : Σ n_i × kapasite_i  ≥  remaining_desi

    Returns: {araç_adı: adet, ...}
    """
    n = len(VEHICLE_NAMES)  # 4

    # Birim maliyetler (TL) ve kapasiteler
    costs = [
        params["spot_daily"][v] + distance_km * params["spot_km"][v]
        for v in VEHICLE_NAMES
    ]
    caps = [params["capacity"][v] for v in VEHICLE_NAMES]

    # CP-SAT tamsayı katsayılarla çalışır; kesirli değerleri ölçekleyelim.
    cap_scale = 1
    for v in caps + [remaining_desi]:
        if abs(v - round(v)) > 1e-6:
            cap_scale = 100
            break

    cost_scale = 100  # kuruş seviyesinde çözüm için
    scaled_caps = [int(round(c * cap_scale)) for c in caps]
    scaled_remaining = int(math.ceil(remaining_desi * cap_scale))
    scaled_costs = [int(round(c * cost_scale)) for c in costs]

    min_cap = max(1, min(scaled_caps))
    max_vehicles = max(1, math.ceil(scaled_remaining / min_cap))

    model = cp_model.CpModel()
    vars_n = [
        model.NewIntVar(0, max_vehicles, f"n_{i}")
        for i in range(n)
    ]

    # Kapasite kısıtı: Σ cap_i * n_i >= remaining
    model.Add(sum(scaled_caps[i] * vars_n[i] for i in range(n)) >= scaled_remaining)

    # Amaç: toplam spot maliyetini minimize et
    model.Minimize(sum(scaled_costs[i] * vars_n[i] for i in range(n)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    solver.parameters.num_search_workers = 8

    try:
        status = solver.Solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {v: int(solver.Value(vars_n[i])) for i, v in enumerate(VEHICLE_NAMES)}
    except Exception:
        pass

    # ─── Greedy fallback ────────────────────────────────────────────
    return _greedy_fallback(remaining_desi, distance_km, params)


def _greedy_fallback(
    remaining_desi: float,
    distance_km: float,
    params: dict,
) -> dict:
    """
    ILP çözülemezse en düşük desi-başı maliyetli araçtan başlayarak
    greedy atama yapar.
    """
    cost_per_desi = []
    for v in VEHICLE_NAMES:
        unit_cost = params["spot_daily"][v] + distance_km * params["spot_km"][v]
        cpd = unit_cost / params["capacity"][v]
        cost_per_desi.append((cpd, v))
    cost_per_desi.sort()  # en düşük desi-başı maliyet önce

    result = {v: 0 for v in VEHICLE_NAMES}
    leftover = remaining_desi
    for _, v in cost_per_desi:
        if leftover <= 0:
            break
        cap = params["capacity"][v]
        need = math.ceil(leftover / cap)
        result[v] = need
        leftover -= need * cap
    return result


# ──────────────────────────────────────────────────────────────────────
# Ana optimizasyon fonksiyonu
# ──────────────────────────────────────────────────────────────────────

def run_optimization(
    forecast_df: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, float, float, float]:
    """
    Araç planlama optimizasyonunu çalıştırır.

    Parameters
    ----------
    forecast_df : pd.DataFrame, optional
        Tahmin verisi. None ise Tahminlenen_Talep.xlsx'den okunur.

    Returns
    -------
    planning_df : pd.DataFrame   – Detaylı planlama tablosu
    total_cost  : float           – Toplam maliyet (TL)
    kiralik_cost: float           – Toplam kiralık maliyet (TL)
    spot_cost   : float           – Toplam spot maliyet (TL)
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # ── 1. Tahmin verisini yükle ─────────────────────────────────────
    if forecast_df is None:
        fpath = _find_file(base_dir, "Tahmin")
        forecast_df = pd.read_excel(fpath)
        _safe_print(f"[OK] Tahmin dosyasi yuklendi: {os.path.basename(fpath)}")

    forecast_df = _standardize_forecast_columns(forecast_df)

    # ── 2. Koordinatlar & mesafe haritası ────────────────────────────
    cpath = _find_file(base_dir, "Koordinat")
    coord_df = pd.read_excel(cpath)
    _safe_print(f"[OK] Koordinat dosyasi yuklendi: {os.path.basename(cpath)}")
    coord_df["Transfer Merkezi"] = coord_df["Transfer Merkezi"].astype(str).str.strip()
    city_set = set(coord_df["Transfer Merkezi"].tolist())
    dist_map = build_distance_map(coord_df)

    # Şehir kısıtı
    forecast_df, excluded = _filter_forecast_by_cities(forecast_df, city_set)
    if excluded > 0:
        _safe_print(f"[!] {excluded} satir resmi sehir listesinde olmadigi icin dislandi.")

    # ── 3. Araç parametreleri ────────────────────────────────────────
    params = _load_vehicle_params(base_dir)

    # ── 4. Kiralık araçlar ───────────────────────────────────────────
    rental_df = _load_rental_vehicles(base_dir)
    rental_df = rental_df[
        rental_df[rental_df.columns[0]].astype(str).str.strip().isin(city_set)
        & rental_df[rental_df.columns[1]].astype(str).str.strip().isin(city_set)
    ].copy()
    rental_lookup = _build_rental_lookup(rental_df)
    rental_pool, initial_by_route = _build_rental_pool(rental_lookup)

    # ── 5. Güzergah analizleri ───────────────────────────────────────
    demand_summary = _summarize_routes_by_demand(forecast_df)
    route_demand_map = {
        (r["Cikis"], r["Varis"]): float(r["Toplam Talep Desi"])
        for _, r in demand_summary.iterrows()
    }

    baseline_planning = _run_baseline_planning(forecast_df, dist_map, params, rental_lookup)
    cost_summary = _summarize_routes_by_cost(baseline_planning)

    # ── 6. Multi-drop routing + dinamik kiralik dagitimi ─────────────
    route_agg = {}
    move_rows = []
    multi_drop_rows = []

    for day, day_df in forecast_df.groupby("Tarih"):
        allocation, required_counts = _allocate_rental_pool_to_origins(
            day_df, dist_map, params, rental_pool
        )

        final_by_route = {}

        for origin in sorted(day_df["Cikis"].unique()):
            nodes = _build_nodes_for_origin(day_df, origin, params)
            if not nodes:
                continue

            vehicles = []
            for v in VEHICLE_NAMES:
                rental_count = allocation.get(origin, {}).get(v, 0)
                req_count = required_counts.get(origin, {}).get(v, 0)
                spot_count = max(req_count - rental_count, 0)

                for _ in range(rental_count):
                    vehicles.append({
                        "type": v,
                        "category": "Kiralik",
                        "capacity": params["capacity"][v],
                        "cost_per_km": params["kiralik_km"][v],
                        "fixed_cost": params["kiralik_daily"][v],
                    })
                for _ in range(spot_count):
                    vehicles.append({
                        "type": v,
                        "category": "Spot",
                        "capacity": params["capacity"][v],
                        "cost_per_km": params["spot_km"][v],
                        "fixed_cost": params["spot_daily"][v],
                    })

            assignments, md_rows, route_vehicle_counts = _solve_routing_for_origin(
                day, origin, nodes, vehicles, dist_map, params
            )
            multi_drop_rows.extend(md_rows)

            for route_key, counts in route_vehicle_counts.items():
                final_by_route.setdefault(route_key, {v: 0 for v in VEHICLE_NAMES})
                for v in VEHICLE_NAMES:
                    final_by_route[route_key][v] += counts["Kiralik"].get(v, 0)

            for assignment in assignments:
                route_key = assignment["route_key"]
                day_key = (day, route_key[0], route_key[1])
                if day_key not in route_agg:
                    route_agg[day_key] = {
                        "Tarih": day,
                        "Çıkış Transfer Merkezi": route_key[0],
                        "Varış Transfer Merkezi": route_key[1],
                        "Taşınan Desi": 0.0,
                        "Mesafe (km)": round(dist_map.get(route_key, 0.0), 2),
                        "Kiralık Tır": 0,
                        "Kiralık Kamyon": 0,
                        "Kiralık Hafif Kamyon": 0,
                        "Kiralık Kamyonet": 0,
                        "Spot Tır": 0,
                        "Spot Kamyon": 0,
                        "Spot Hafif Kamyon": 0,
                        "Spot Kamyonet": 0,
                        "Kiralık Maliyet (TL)": 0.0,
                        "Spot Maliyet (TL)": 0.0,
                        "Toplam Maliyet (TL)": 0.0,
                    }

                share = 0.0
                if assignment["route_demand"] > 0:
                    share = assignment["demand"] / assignment["route_demand"]

                cost_share = assignment["route_cost"] * share
                route_agg[day_key]["Taşınan Desi"] += assignment["demand"]
                route_agg[day_key]["Toplam Maliyet (TL)"] += cost_share

                if assignment["vehicle"]["category"] == "Kiralik":
                    route_agg[day_key]["Kiralık Maliyet (TL)"] += cost_share
                else:
                    route_agg[day_key]["Spot Maliyet (TL)"] += cost_share

            for route_key, counts in route_vehicle_counts.items():
                day_key = (day, route_key[0], route_key[1])
                if day_key not in route_agg:
                    continue
                for v in VEHICLE_NAMES:
                    route_agg[day_key][f"Kiralık {v}"] += counts["Kiralik"].get(v, 0)
                    route_agg[day_key][f"Spot {v}"] += counts["Spot"].get(v, 0)

        move_df = _build_move_summary(day, initial_by_route, final_by_route, route_demand_map)
        if not move_df.empty:
            move_rows.append(move_df)

    # ── 7. Planlama tablosu ──────────────────────────────────────────
    planning_df = pd.DataFrame(list(route_agg.values()))
    if not planning_df.empty:
        planning_df["Kiralık Araç Sayısı"] = (
            planning_df[["Kiralık Tır", "Kiralık Kamyon", "Kiralık Hafif Kamyon", "Kiralık Kamyonet"]]
            .sum(axis=1)
            .astype(int)
        )
        planning_df["Spot Araçlar"] = planning_df.apply(
            lambda r: "; ".join([
                f"Tır: {int(r['Spot Tır'])}",
                f"Kamyon: {int(r['Spot Kamyon'])}",
                f"Hafif Kamyon: {int(r['Spot Hafif Kamyon'])}",
                f"Kamyonet: {int(r['Spot Kamyonet'])}",
            ]),
            axis=1,
        )

    # Toplamlar
    total_kiralik = planning_df["Kiralık Maliyet (TL)"].sum() if not planning_df.empty else 0.0
    total_spot = planning_df["Spot Maliyet (TL)"].sum() if not planning_df.empty else 0.0
    total_cost = planning_df["Toplam Maliyet (TL)"].sum() if not planning_df.empty else 0.0

    # ── 8. Excel çıktısı ────────────────────────────────────────────
    output_path = os.path.join(base_dir, "Arac_Planlama_Yeni.xlsx")

    route_summary = (
        planning_df
        .groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"], as_index=False)
        .agg({
            "Kiralık Maliyet (TL)": "sum",
            "Spot Maliyet (TL)": "sum",
            "Toplam Maliyet (TL)": "sum",
            "Taşınan Desi": "sum",
        })
        .rename(columns={"Taşınan Desi": "Toplam Taşınan Desi"})
        .sort_values("Toplam Maliyet (TL)", ascending=False)
    )

    day_summary = (
        planning_df
        .groupby("Tarih", as_index=False)
        .agg({
            "Kiralık Maliyet (TL)": "sum",
            "Spot Maliyet (TL)": "sum",
            "Toplam Maliyet (TL)": "sum",
            "Taşınan Desi": "sum",
        })
        .rename(columns={"Taşınan Desi": "Toplam Taşınan Desi"})
        .sort_values("Tarih")
    )

    overall = pd.DataFrame([
        {"Metrik": "Toplam Kiralık Maliyet (TL)", "Değer": round(total_kiralik, 2)},
        {"Metrik": "Toplam Spot Maliyet (TL)", "Değer": round(total_spot, 2)},
        {"Metrik": "Toplam Maliyet (TL)", "Değer": round(total_cost, 2)},
        {"Metrik": "Toplam Guzergah Sayisi", "Değer": len(route_summary)},
        {"Metrik": "Toplam Gun Sayisi", "Değer": len(day_summary)},
        {"Metrik": "Toplam Kayit Sayisi", "Değer": len(planning_df)},
    ])

    move_df = pd.concat(move_rows, ignore_index=True) if move_rows else pd.DataFrame()
    if move_df.empty:
        move_df = pd.DataFrame(columns=[
            "Tarih",
            "Araç Türü",
            "Kaynak Güzergah",
            "Hedef Güzergah",
            "Adet",
            "Kaynak Talep (Desi)",
            "Hedef Talep (Desi)",
        ])

    md_df = pd.DataFrame(multi_drop_rows)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        planning_df.to_excel(writer, sheet_name="Detay", index=False)

        startrow = 0
        overall.to_excel(writer, sheet_name="Özet", index=False, startrow=startrow)
        startrow += len(overall) + 2

        ws = writer.sheets["Özet"]
        ws.cell(row=startrow + 1, column=1, value="Guzergah Bazli Maliyet")
        startrow += 1
        route_summary.to_excel(writer, sheet_name="Özet", index=False, startrow=startrow)
        startrow += len(route_summary) + 2

        ws.cell(row=startrow + 1, column=1, value="Gun Bazli Maliyet")
        startrow += 1
        day_summary.to_excel(writer, sheet_name="Özet", index=False, startrow=startrow)

        demand_summary.to_excel(writer, sheet_name="Analiz_Yogunluk", index=False)
        cost_summary.to_excel(writer, sheet_name="Analiz_Maliyet", index=False)
        move_df.to_excel(writer, sheet_name="Filo_Kaydirma", index=False)
        md_df.to_excel(writer, sheet_name="Multi_Drop_Rotalar", index=False)

    _safe_print(f"\n[OK] Cikti dosyasi olusturuldu: {output_path}")

    # ── 9. Özet istatistikler ────────────────────────────────────────
    _safe_print("\n" + "=" * 60)
    _safe_print("  ARAC PLANLAMA OZETI")
    _safe_print("=" * 60)
    _safe_print(f"  Toplam Kiralik Maliyet : {total_kiralik:>15,.2f} TL")
    _safe_print(f"  Toplam Spot Maliyet    : {total_spot:>15,.2f} TL")
    _safe_print(f"  TOPLAM MALIYET         : {total_cost:>15,.2f} TL")
    _safe_print("-" * 60)
    _safe_print(f"  Guzergah sayisi        : {len(route_summary)}")
    _safe_print(f"  Gun sayisi             : {len(day_summary)}")
    _safe_print(f"  Toplam kayit           : {len(planning_df)}")
    _safe_print("=" * 60)

    if not demand_summary.empty:
        _safe_print("\n  Talebe gore en yogun 5 guzergah:")
        for _, r in demand_summary.head(5).iterrows():
            _safe_print(f"    {r['Cikis']:>12s} -> {r['Varis']:<12s}  {r['Toplam Talep Desi']:>12,.0f} desi")

    if not cost_summary.empty:
        _safe_print("\n  Onceki optimizasyona gore en pahali 5 guzergah:")
        for _, r in cost_summary.head(5).iterrows():
            _safe_print(
                f"    {r['Çıkış Transfer Merkezi']:>12s} -> {r['Varış Transfer Merkezi']:<12s}  "
                f"{r['Toplam Maliyet (TL)']:>12,.2f} TL"
            )

    if not move_df.empty:
        _safe_print("\n  Filo Kaydirma Ozeti (ilk 10 kayit):")
        for _, r in move_df.head(10).iterrows():
            day_str = pd.to_datetime(r["Tarih"]).date()
            _safe_print(
                f"    {day_str} | {r['Araç Türü']}: {r['Kaynak Güzergah']} -> "
                f"{r['Hedef Güzergah']} ({int(r['Adet'])})"
            )

    return planning_df, total_cost, total_kiralik, total_spot


# ──────────────────────────────────────────────────────────────────────
# Standalone çalıştırma
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    planning_df, total_cost, kiralik_cost, spot_cost = run_optimization()
