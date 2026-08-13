import json
import math
from datetime import datetime

import flet as ft
import flet_map as ftm
from geopy.geocoders import Nominatim
import geopy.geocoders

# Adjust Geocoder options
geopy.geocoders.options.default_user_agent = "meshwar_calculator_egypt/5.0"
geolocator = Nominatim()

# Storage keys
K_PROFILES, K_LAST, K_TOLLS, K_PAX, K_HIST = (
    "meshwar.profiles", "meshwar.last_profile", "meshwar.tolls", "meshwar.pax", "meshwar.history"
)a
DEFAULT_PROFILES = {"سيارتي": {"fuel_price": 15.00, "kpl": 11.0}}

# Styling Palette
PRIMARY_COLOR = ft.Colors.TEAL_400
BG_COLOR = "#0D1117"
CARD_BG = "#161B22"
BORDER_COLOR = "#30363D"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def rideshare_estimate(p, d, base_fare, per_km, per_min, min_fare):
    dist_km = haversine_km(*p, *d) * 1.3
    minutes = (dist_km / 25) * 60
    return max(min_fare, base_fare + dist_km * per_km + minutes * per_min)


def fmt_egp(amount):
    return f"{amount:,.2f} ج.م"


async def main(page: ft.Page):
    page.title = "مشوار - حاسبة الرحلات والتوصيل"
    page.window.width, page.window.height = 540, 940
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 0
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG_COLOR
    page.rtl = True  # Enable Right-to-Left for Arabic layout

    # Storage Helpers
    async def get_json(key, default):
        try:
            raw = await page.shared_preferences.get(key)
            return json.loads(raw) if raw is not None else default
        except Exception:
            return default

    async def set_json(key, value):
        await page.shared_preferences.set(key, json.dumps(value))

    async def get_str(key, default):
        try:
            val = await page.shared_preferences.get(key)
            return val if val is not None else default
        except Exception:
            return default

    profiles = await get_json(K_PROFILES, DEFAULT_PROFILES)
    last_profile = await get_str(K_LAST, next(iter(profiles)))
    if last_profile not in profiles:
        last_profile = next(iter(profiles))
    history = await get_json(K_HIST, [])

    state = {"pickup": (30.0444, 31.2357), "dropoff": (30.1219, 31.4056)}

    # =============== TAB 1: TRIP PLANNER ===============
    pickup_input = ft.TextField(
        label="مكان التحرك", value="ميدان التحرير، القاهرة", expand=True,
        border_radius=10, border_color=BORDER_COLOR
    )
    dropoff_input = ft.TextField(
        label="وجهة الوصول", value="مطار القاهرة الدولي", expand=True,
        border_radius=10, border_color=BORDER_COLOR
    )
    distance_input = ft.TextField(
        label="المسافة (كيلومتر)", value="22.5", keyboard_type=ft.KeyboardType.NUMBER,
        border_radius=10, border_color=BORDER_COLOR
    )
    geo_status = ft.Text("", size=12, italic=True)
    geo_progress = ft.ProgressRing(width=14, height=14, stroke_width=2, visible=False)

    pin_toggle = ft.SegmentedButton(
        selected=["pickup"],
        segments=[
            ft.Segment(value="pickup", label=ft.Text("تحديد نقطة التحرك"), icon=ft.Icon(ft.Icons.LOCATION_ON)),
            ft.Segment(value="dropoff", label=ft.Text("تحديد نقطة الوصول"), icon=ft.Icon(ft.Icons.FLAG)),
        ],
    )

    pax_input = ft.TextField(
        label="الركاب", value=await get_str(K_PAX, "3"),
        keyboard_type=ft.KeyboardType.NUMBER, width=90, text_align=ft.TextAlign.CENTER,
        border_radius=10, border_color=BORDER_COLOR
    )

    def step_pax(delta):
        try:
            v = max(1, int(pax_input.value) + delta)
        except ValueError:
            v = 1
        pax_input.value = str(v)
        page.update()

    pax_row = ft.Row([
        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=PRIMARY_COLOR, on_click=lambda e: step_pax(-1)),
        pax_input,
        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, icon_color=PRIMARY_COLOR, on_click=lambda e: step_pax(1)),
    ])

    result_texts = {}
    result_cards = {}

    def make_result_card(name, icon, accent):
        total_txt = ft.Text("—", size=15, weight=ft.FontWeight.BOLD)
        per_txt = ft.Text("—", size=15, weight=ft.FontWeight.BOLD, color=accent)
        result_texts[name] = (total_txt, per_txt)

        card = ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(icon, size=18, color=accent), ft.Text(name, weight=ft.FontWeight.BOLD, size=13)]),
                ft.Divider(color=BORDER_COLOR, height=8),
                ft.Text("الإجمالي", size=10, color=ft.Colors.GREY_400),
                total_txt,
                ft.Text("للفرد", size=10, color=ft.Colors.GREY_400),
                per_txt,
            ], spacing=2),
            padding=12, bgcolor=CARD_BG, border=ft.Border.all(1, BORDER_COLOR), border_radius=12, expand=True,
        )
        result_cards[name] = card
        return card

    car_card = make_result_card("سيارة خاصة", ft.Icons.DIRECTIONS_CAR, ft.Colors.GREEN_400)
    uber_card = make_result_card("أوبر مصر", ft.Icons.LOCAL_TAXI, ft.Colors.LIGHT_BLUE_400)
    careem_card = make_result_card("كريم", ft.Icons.TWO_WHEELER, ft.Colors.AMBER_400)
    recommendation_txt = ft.Text("", size=13, weight=ft.FontWeight.W_600)

    def highlight_cheapest(name):
        for c in result_cards.values():
            c.border = ft.Border.all(1, BORDER_COLOR)
        result_cards[name].border = ft.Border.all(2, ft.Colors.GREEN_400)

    pickup_marker = ftm.Marker(
        content=ft.Icon(ft.Icons.LOCATION_ON, color=ft.Colors.GREEN_400, size=32),
        coordinates=ftm.MapLatitudeLongitude(*state["pickup"])
    )
    dropoff_marker = ftm.Marker(
        content=ft.Icon(ft.Icons.FLAG, color=ft.Colors.RED_400, size=32),
        coordinates=ftm.MapLatitudeLongitude(*state["dropoff"])
    )

    def recompute_distance():
        dist = haversine_km(*state["pickup"], *state["dropoff"]) * 1.3
        distance_input.value = f"{dist:.1f}"
        return dist

    def handle_map_tap(e: ftm.MapTapEvent):
        lat, lon = e.coordinates.latitude, e.coordinates.longitude
        sel = pin_toggle.selected
        mode = sel[0] if isinstance(sel, (list, set)) else sel
        if mode == "pickup":
            state["pickup"] = (lat, lon)
            pickup_marker.coordinates = ftm.MapLatitudeLongitude(lat, lon)
            pickup_input.value = f"{lat:.4f}, {lon:.4f}"
        else:
            state["dropoff"] = (lat, lon)
            dropoff_marker.coordinates = ftm.MapLatitudeLongitude(lat, lon)
            dropoff_input.value = f"{lat:.4f}, {lon:.4f}"
        dist = recompute_distance()
        geo_status.value, geo_status.color = f"تم تحديد الدبوس. المسافة المقدرة: {dist:.1f} كم", ft.Colors.GREEN_400
        page.update()

    map_control = ftm.Map(
        expand=False, height=220,
        initial_center=ftm.MapLatitudeLongitude(30.05, 31.30), initial_zoom=10,
        on_tap=handle_map_tap,
        layers=[
            ftm.TileLayer(
                url_template="https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
                user_agent_package_name="meshwar_app/5.0"
            ),
            ftm.MarkerLayer(markers=[pickup_marker, dropoff_marker]),
        ],
    )

    def swap_locations(e):
        pickup_input.value, dropoff_input.value = dropoff_input.value, pickup_input.value
        state["pickup"], state["dropoff"] = state["dropoff"], state["pickup"]
        pickup_marker.coordinates = ftm.MapLatitudeLongitude(*state["pickup"])
        dropoff_marker.coordinates = ftm.MapLatitudeLongitude(*state["dropoff"])
        recompute_distance()
        page.update()

    def auto_lookup_distance(e):
        p_addr, d_addr = pickup_input.value.strip(), dropoff_input.value.strip()
        if not p_addr or not d_addr:
            geo_status.value, geo_status.color = "يرجى كتابة العناوين أو التحديد عبر الخريطة.", ft.Colors.ORANGE_400
            page.update()
            return
        geo_status.value, geo_status.color = "جاري البحث عن العناوين...", ft.Colors.BLUE_300
        geo_progress.visible = True
        page.update()
        try:
            loc1, loc2 = geolocator.geocode(p_addr), geolocator.geocode(d_addr)
            if loc1 and loc2:
                state["pickup"] = (loc1.latitude, loc1.longitude)
                state["dropoff"] = (loc2.latitude, loc2.longitude)
                pickup_marker.coordinates = ftm.MapLatitudeLongitude(*state["pickup"])
                dropoff_marker.coordinates = ftm.MapLatitudeLongitude(*state["dropoff"])
                dist_km = recompute_distance()
                geo_status.value = f"تم العثور! المسافة المقدرة: {dist_km:.1f} كم"
                geo_status.color = ft.Colors.GREEN_400
            else:
                geo_status.value = "لم يتم العثور على العنوان. جرب تحديد الموقع بالدبوس."
                geo_status.color = ft.Colors.RED_400
        except Exception as ex:
            geo_status.value, geo_status.color = f"خطأ بالبحث: {ex}", ft.Colors.RED_400
        finally:
            geo_progress.visible = False
            page.update()

    def active_profile():
        name = profile_dropdown.value or last_profile
        return name, profiles.get(name, next(iter(profiles.values())))

    async def calculate_costs(e):
        try:
            distance_km = float(distance_input.value)
            _, prof = active_profile()
            fuel_price, kpl = float(prof["fuel_price"]), float(prof["kpl"])
            tolls = float(tolls_input.value) if tolls_input.value else 0.0
            passengers = max(1, int(pax_input.value))
            if distance_km <= 0 or kpl <= 0:
                raise ValueError

            total_car = (distance_km / kpl) * fuel_price + tolls
            total_uber = rideshare_estimate(state["pickup"], state["dropoff"], 15.00, 5.50, 0.85, 35.00)
            total_careem = rideshare_estimate(state["pickup"], state["dropoff"], 14.00, 5.25, 0.80, 32.00)

            totals = {"سيارة خاصة": total_car, "أوبر مصر": total_uber, "كريم": total_careem}
            for name, total in totals.items():
                total_txt, per_txt = result_texts[name]
                total_txt.value = fmt_egp(total)
                per_txt.value = fmt_egp(total / passengers)

            cheapest_name, cheapest_val = min(totals.items(), key=lambda kv: kv[1])
            recommendation_txt.value = (
                f"الخيار الأوفر: {cheapest_name} بتكلفة {fmt_egp(cheapest_val)} "
                f"({fmt_egp(cheapest_val / passengers)} للفرد)."
            )
            recommendation_txt.color = ft.Colors.GREEN_400
            highlight_cheapest(cheapest_name)

            await page.shared_preferences.set(K_PAX, pax_input.value)
            await page.shared_preferences.set(K_TOLLS, tolls_input.value)

            history.insert(0, {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "pickup": pickup_input.value, "dropoff": dropoff_input.value,
                "distance": round(distance_km, 1),
                "car": round(total_car, 2), "uber": round(total_uber, 2), "careem": round(total_careem, 2),
                "cheapest": cheapest_name,
            })
            del history[10:]
            await set_json(K_HIST, history)
            refresh_history_list()
            page.update()
        except ValueError:
            recommendation_txt.value = "يرجى التأكد من إدخال أرقام صحيحة للمسافة، سعر الوقود، والركاب."
            recommendation_txt.color = ft.Colors.RED_400
            page.update()

    geo_btn = ft.OutlinedButton("بحث عن العنوان", icon=ft.Icons.SEARCH, on_click=auto_lookup_distance)
    swap_btn = ft.IconButton(ft.Icons.SWAP_HORIZ, tooltip="تبديل أماكن التحرك والوصول", on_click=swap_locations)
    calc_btn = ft.Button(
        "حساب ومقارنة الأسعار", icon=ft.Icons.CALCULATE, on_click=calculate_costs,
        color=ft.Colors.WHITE, bgcolor=PRIMARY_COLOR, width=300, height=45
    )

    trip_tab = ft.Container(
        ft.Column([
            ft.Text("مسار الرحلة", weight=ft.FontWeight.BOLD, size=14, color=PRIMARY_COLOR),
            pin_toggle,
            ft.Container(content=map_control, border=ft.Border.all(1, BORDER_COLOR), border_radius=12),
            ft.Row([pickup_input, swap_btn, dropoff_input]),
            ft.Row([geo_btn, geo_progress, geo_status]),
            distance_input,
            ft.Divider(color=BORDER_COLOR),
            ft.Text("تفاصيل الرحلة", weight=ft.FontWeight.BOLD, size=14, color=PRIMARY_COLOR),
            ft.Row([ft.Text("عدد الركاب:"), pax_row], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(content=calc_btn, alignment=ft.Alignment(0, 0), margin=ft.Margin(top=6, bottom=6)),
            ft.Divider(color=BORDER_COLOR),
            ft.Text("مقارنة التكاليف", size=15, weight=ft.FontWeight.BOLD),
            ft.Row([car_card, uber_card, careem_card]),
            ft.Container(content=recommendation_txt, margin=ft.Margin(top=8)),
        ], spacing=10),
        padding=16,
    )

    # =============== TAB 2: VEHICLE PROFILES ===============
    profile_dropdown = ft.Dropdown(
        label="ملف السيارة الحالي", value=last_profile,
        options=[ft.dropdown.Option(n) for n in profiles], expand=True,
        border_radius=10, border_color=BORDER_COLOR
    )
    profile_name_input = ft.TextField(label="اسم الملف (مثلاً: سيارتي)", value=last_profile, expand=True, border_radius=10, border_color=BORDER_COLOR)
    fuel_price_input = ft.TextField(
        label="سعر لتر البنزين (ج.م)", value=str(profiles[last_profile]["fuel_price"]),
        keyboard_type=ft.KeyboardType.NUMBER, border_radius=10, border_color=BORDER_COLOR
    )
    kpl_input = ft.TextField(
        label="استهلاك البنزين (كم/لتر)", value=str(profiles[last_profile]["kpl"]),
        keyboard_type=ft.KeyboardType.NUMBER, border_radius=10, border_color=BORDER_COLOR
    )
    tolls_input = ft.TextField(
        label="رسوم الطرق والباركينج الإفتراضية (ج.م)", value=await get_str(K_TOLLS, "20.00"),
        keyboard_type=ft.KeyboardType.NUMBER, border_radius=10, border_color=BORDER_COLOR
    )
    profile_status = ft.Text("", size=12, italic=True)

    def refresh_profile_dropdown(select=None):
        profile_dropdown.options = [ft.dropdown.Option(n) for n in profiles]
        profile_dropdown.value = select or profile_dropdown.value

    async def on_profile_selected(e):
        name, prof = active_profile()
        profile_name_input.value = name
        fuel_price_input.value = str(prof["fuel_price"])
        kpl_input.value = str(prof["kpl"])
        await page.shared_preferences.set(K_LAST, name)
        page.update()

    profile_dropdown.on_change = on_profile_selected

    async def save_profile(e):
        try:
            name = profile_name_input.value.strip()
            fuel_price, kpl = float(fuel_price_input.value), float(kpl_input.value)
            if not name or kpl <= 0:
                raise ValueError
            profiles[name] = {"fuel_price": fuel_price, "kpl": kpl}
            await set_json(K_PROFILES, profiles)
            await page.shared_preferences.set(K_LAST, name)
            refresh_profile_dropdown(select=name)
            profile_status.value, profile_status.color = f"تم حفظ الملف '{name}'.", ft.Colors.GREEN_400
        except ValueError:
            profile_status.value = "يرجى كتابة اسم صحيح وسعر واستهلاك وقود منطقيين."
            profile_status.color = ft.Colors.RED_400
        page.update()

    async def delete_profile(e):
        name = profile_dropdown.value
        if len(profiles) <= 1:
            profile_status.value, profile_status.color = "يجب ترك ملف سيارة واحد على الأقل.", ft.Colors.ORANGE_400
            page.update()
            return
        profiles.pop(name, None)
        await set_json(K_PROFILES, profiles)
        new_selected = next(iter(profiles))
        await page.shared_preferences.set(K_LAST, new_selected)
        refresh_profile_dropdown(select=new_selected)
        await on_profile_selected(None)
        profile_status.value, profile_status.color = f"تم حذف الملف '{name}'.", ft.Colors.GREEN_400
        page.update()

    vehicle_tab = ft.Container(
        ft.Column([
            ft.Text("احفظ بيانات استهلاك وسيارة خاصة حتى لا تضطر لإدخالها كل مرة.", size=12, color=ft.Colors.GREY_400),
            profile_dropdown,
            ft.Divider(color=BORDER_COLOR),
            profile_name_input,
            ft.Row([fuel_price_input, kpl_input]),
            ft.Row([
                ft.Button("حفظ الملف", icon=ft.Icons.SAVE, on_click=save_profile, bgcolor=PRIMARY_COLOR, color=ft.Colors.WHITE),
                ft.OutlinedButton("حذف الملف", icon=ft.Icons.DELETE_OUTLINE, on_click=delete_profile),
            ]),
            profile_status,
            ft.Divider(color=BORDER_COLOR),
            ft.Text("الإعدادات الإفتراضية للرحلات", weight=ft.FontWeight.BOLD, size=13, color=PRIMARY_COLOR),
            tolls_input,
        ], spacing=10),
        padding=16,
    )

    # =============== TAB 3: HISTORY ===============
    history_list = ft.ListView(spacing=8, height=520)

    async def clear_history(e):
        history.clear()
        await set_json(K_HIST, history)
        refresh_history_list()
        page.update()

    def refresh_history_list():
        history_list.controls.clear()
        if not history:
            history_list.controls.append(ft.Text("لا توجد رحلات مسجلة بعد.", italic=True, color=ft.Colors.GREY_400))
        for trip in history:
            history_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text(f"{trip['pickup']} ← {trip['dropoff']}", weight=ft.FontWeight.BOLD, expand=True, size=13),
                            ft.Text(trip["time"], size=10, color=ft.Colors.GREY_400),
                        ]),
                        ft.Text(f"المسافة: {trip['distance']} كم", size=11, color=ft.Colors.GREY_300),
                        ft.Row([
                            ft.Text(f"خاصة: {fmt_egp(trip['car'])}", size=11),
                            ft.Text(f"أوبر: {fmt_egp(trip['uber'])}", size=11),
                            ft.Text(f"كريم: {fmt_egp(trip['careem'])}", size=11),
                        ], spacing=10),
                        ft.Text(f"الأوفر: {trip['cheapest']}", size=11, color=ft.Colors.GREEN_400, weight=ft.FontWeight.BOLD),
                    ], spacing=4),
                    padding=10, bgcolor=CARD_BG, border=ft.Border.all(1, BORDER_COLOR), border_radius=10,
                )
            )

    refresh_history_list()

    history_tab = ft.Container(
        ft.Column([
            ft.Row([
                ft.Text("آخر 10 رحلات تم حسابها", weight=ft.FontWeight.BOLD, size=13, color=PRIMARY_COLOR, expand=True),
                ft.TextButton("مسح السجل", icon=ft.Icons.DELETE_SWEEP, on_click=clear_history),
            ]),
            history_list,
        ], spacing=8),
        padding=16,
    )

    # =============== LAYOUT & NAVIGATION ===============
    tabs = {0: trip_tab, 1: vehicle_tab, 2: history_tab}
    content_area = ft.Container(content=trip_tab, expand=True)

    def on_nav_change(e):
        content_area.content = tabs[e.control.selected_index]
        page.update()

    page.navigation_bar = ft.NavigationBar(
        selected_index=0, on_change=on_nav_change,
        bgcolor=CARD_BG,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.MAP, label="الرحلة"),
            ft.NavigationBarDestination(icon=ft.Icons.DIRECTIONS_CAR, label="السيارات"),
            ft.NavigationBarDestination(icon=ft.Icons.HISTORY, label="السجل"),
        ],
    )
    
    page.appbar = ft.AppBar(
        title=ft.Text("مشوار - Meshwar", size=19, weight=ft.FontWeight.BOLD),
        center_title=False, bgcolor=CARD_BG
    )
    page.add(content_area)


if __name__ == "__main__":
    ft.run(main)