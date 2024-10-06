from flask import Flask, render_template, request, jsonify
from skyfield.api import Topos, load
# import geopandas as gpd
# from shapely.geometry import Point
from datetime import timedelta
import pystac_client
import planetary_computer
# import rasterio
import requests
import os

app = Flask(__name__)

# Step 1: 設定 AWS S3 連線 (Landsat 數據可從 Amazon S3 公開存取)
# s3_client = boto3.client('s3', region_name='us-west-2')

catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)

# Step 2: 取得 Landsat 衛星的 TLE 資料
stations_url = 'https://celestrak.org/NORAD/elements/resource.txt'
satellites = load.tle_file(stations_url)
landsat_8 = next(sat for sat in satellites if sat.name == 'LANDSAT 8')
landsat_9 = next(sat for sat in satellites if sat.name == 'LANDSAT 9')

ts = load.timescale()

# Step 3: 顯示首頁
@app.route('/')
def index():
    return render_template('index.html')

# Step 4: 設定地理位置，計算 Landsat 衛星經過的時間
@app.route('/satellite_pass', methods=['POST'])
def satellite_pass():
    lat = float(request.json['latitude'])
    lon = float(request.json['longitude'])
    
    location = Topos(latitude_degrees=lat, longitude_degrees=lon)
    t0 = ts.now()
    t1 = ts.utc(t0.utc_datetime() + timedelta(days=1))

    # 計算經過時間
    t, events = landsat_8.find_events(location, t0, t1, altitude_degrees=30.0)
    passes = []
    for ti, event in zip(t, events):
        passes.append({
            'name': 'Landsat 8',
            'time': ti.utc_iso(),
            'event': ('rise', 'culminate', 'set')[event]
        })
    
    t, events = landsat_9.find_events(location, t0, t1, altitude_degrees=30.0)
    for ti, event in zip(t, events):
        passes.append({
            'name': 'Landsat 9',
            'time': ti.utc_iso(),
            'event': ('rise', 'culminate', 'set')[event]
        })

    return jsonify(passes)

# Step 5: 從 AWS S3 獲取 Landsat SR 數據
@app.route('/get_landsat_data', methods=['POST'])
def get_landsat_data():
    lat = float(request.json['latitude'])
    lon = float(request.json['longitude'])

    # print(lat, lon)
    
    # 使用 WRS-2 網格系統來查找經緯度所對應的 Landsat 場景
    # path, row = calculate_wrs2_path_row(lat, lon)

    time_range = "2024-01-01/2025-01-01"

    bbox = [lon-0.005, lat-0.005, lon+0.005, lat+0.005]

    search = catalog.search(collections=["landsat-c2-l2"],
                            bbox=bbox,
                            datetime=time_range,
                            sortby=[{"field": "properties.datetime", "direction": "desc"}]  # 按時間降序排序
                            )
    items = search.get_all_items()
    print(len(items))
    lastest = items[0]
    least_cloud = min(items, key=lambda item: item.properties["eo:cloud_cover"])


    # 回傳數據（可視化或存儲）
    return jsonify({
        # 'path': str(path),
        # 'row': str(row),
        'lastest': lastest.assets["rendered_preview"].href,
        'least_cloud': least_cloud.assets["rendered_preview"].href
        # 'surface_reflectance': band4.tolist()  # 將 numpy array 轉換為列表
    })
    # return jsonify({
    #     'path': str(path),
    #     'row': str(row),
    # })

@app.route('/send_notify', methods=['POST'])
def send_notify():
    token = request.json.get('token')
    message = request.json.get('message')
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'message': message
    }
    
    response = requests.post('https://notify-api.line.me/api/notify', headers=headers, data=data)
    return jsonify(response.json())

# 用於計算 WRS-2 Path 和 Row 的輔助函數 (假設有相關資料庫)
# def calculate_wrs2_path_row(lat, lon):
#     # 讀取 WRS-2 Shapefile (替換為下載的文件路徑)
#     wrs2_shapefile = "WRS2/WRS2_descending.shp"  # Shapefile 檔案路徑
#     wrs2 = gpd.read_file(wrs2_shapefile)

#     # 建立一個經緯度點
#     point = Point(lon, lat)

#     # 查詢包含該點的 path/row 區域
#     wrs2_containing_point = wrs2[wrs2.contains(point)]

#     if not wrs2_containing_point.empty:
#         path = wrs2_containing_point.iloc[0]['PATH']
#         row = wrs2_containing_point.iloc[0]['ROW']
#         print(f"Path: {path}, Row: {row}")
#         return path, row
#     else:
#         print("未找到對應的 Path 和 Row。")
#         return None, None

if __name__ == '__main__':
    app.run(debug=True)
