# DXF Inspection Tool — Công cụ kiểm tra bản vẽ DXF

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28%2B-FF4B4B)](https://streamlit.io)
[![ezdxf](https://img.shields.io/badge/ezdxf-1.2%2B-orange)](https://ezdxf.readthedocs.io)

> Phân tích và kiểm tra các bản vẽ DXF (CAD) cho PCB/cơ khí, phát hiện các kích thước thiếu và đề xuất bổ sung.

---

## 📖 Overview / Tổng quan

**English:** This tool processes DXF (Drawing Exchange Format) files to extract geometric endpoints, classify dimensional constraints, and detect missing measurements using graph algorithms (Floyd-Warshall). It decomposes a 2D CAD drawing into three orthogonal projections (side, top, front) and identifies which dimensions are missing.

**Tiếng Việt:** Công cụ này xử lý file DXF, trích xuất các điểm đầu cuối (endpoint) hình học, phân loại các ràng buộc kích thước (constraint), và phát hiện các kích thước bị thiếu bằng thuật toán Floyd-Warshall. Bản vẽ 2D được chiếu thành 3 hình chiếu (cạnh, trên, trước) để xác định kích thước còn thiếu.

---

## 🏗️ Pipeline Architecture

```
┌─────────────┐
│   File DXF  │
└──────┬──────┘
       ▼
┌─────────────────────────┐
│ 1. endpoint_boards.py   │  Trích xuất endpoints + circles
│    (Stage 1)            │
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 2. dxf_statistical.py   │  Phân loại constraints
│    (Stage 2)            │  distance_x / y / edge / angle / radius / other
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 3. interpolate.py       │  Lan truyền tọa độ (64 iterations)
│    (Stage 3)            │  Suy luận quan hệ giữa các điểm
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 4. projection_3_axis.py │  Chiếu 3 trục (ox, oy, oz)
│    (Stage 4)            │  Side / Top / Front views
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 5. lack_print.py        │  Floyd-Warshall phát hiện thiếu
│    (Stage 5)            │  constraints + offsets
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 6. final_print.py       │  Tạo kích thước cuối cùng
│    (Stage 6)            │  final_distance_x / y / oz
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│   Streamlit UI (app.py) │  Hiển thị kết quả
└─────────────────────────┘
```

---

## 🚀 Installation / Cài đặt

```bash
# Clone repository
git clone https://github.com/tuanvan03/Gr016-solution1.git

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## 🎯 Usage / Sử dụng

```bash
# Khởi chạy Streamlit app
streamlit run app.py
```

Sau đó mở trình duyệt tại địa chỉ hiển thị (mặc định `http://localhost:8501`).

### Các bước sử dụng:
1. **Upload file DXF** qua sidebar
2. Hệ thống tự động chạy pipeline 6 bước
3. Duyệt kết quả qua 6 tabs:
   - 📐 **Bản vẽ**: Hiển thị DXF entities bằng Plotly
   - 📊 **Dữ liệu**: Endpoints, circles, constraints
   - 🔄 **Nội suy**: Kết quả lan truyền tọa độ
   - 📈 **Hình chiếu**: 3-axis projection (ox/oy/oz)
   - 🔍 **Thiếu hụt**: Constraints còn thiếu
   - ✅ **Kết quả**: Kích thước cuối cùng

---

## 📁 File Structure

```
KIEM_TRA_DXF/
├── app.py                  # Streamlit UI (entry point)
├── utils.py                # Shared utility functions
├── endpoint_boards.py      # Stage 1: endpoint extraction
├── dxf_statistical.py      # Stage 2: dimension classification
├── interpolate.py          # Stage 3: coordinate propagation
├── projection_3_axis.py    # Stage 4: 3-axis projection
├── lack_print.py           # Stage 5: missing constraints (Floyd-Warshall)
├── final_print.py          # Stage 6: final dimensions
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── lack6.dxf               # Test data
└── lack7.dxf               # Test data
```

---

## 🔬 Key Algorithms / Thuật toán chính

| Algorithm | File | Purpose |
|-----------|------|---------|
| **Floyd-Warshall** | `lack_print.py` | Tìm tất cả constraints còn thiếu để đảm bảo kết nối đầy đủ |
| **Iterative Expansion** | `interpolate.py` | 64 vòng lan truyền tọa độ qua quan hệ hình học |
| **Merge Overlapping Intervals** | `interpolate.py` | Gom các đoạn thẳng trùng lặp trên trục |
| **3-Axis Projection** | `projection_3_axis.py` | Chiếu bản vẽ 2D thành 3 hình chiếu |

---

## 📊 Dimension Types / Loại kích thước

| `dim_type` | Kind | Mô tả |
|------------|------|-------|
| 0 (angle=0/180) | `distance_x` | Kích thước chiều X |
| 0 (angle=90) | `distance_y` | Kích thước chiều Y |
| 1 | `distance_edge` | Cạnh chéo |
| 2 | `distance_angle` | Góc |
| 3 | `distance_radius` | Đường tròn có đường kính |
| 4–8 | `distance_other` | Khác (bán kính, v.v.) |

---

## 🧪 Test

Mở app và upload các file test:
- `lack6.dxf` — Bản vẽ đơn giản
- `lack7.dxf` — Bản vẽ phức tạp (127 entities, 105 endpoints)

---

## 📦 Dependencies

- **ezdxf** — Đọc/parse file DXF
- **Streamlit** — Web UI framework
- **Plotly** — Interactive charts & SVG rendering
- **Pandas** — Data tables
- **NumPy** — Numerical operations

---

## 📝 License
Gr016 with love <3
MIT License
# Gr016-solution1
