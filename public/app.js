import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-app.js";
import { getFirestore, collection, getDocs, query, orderBy } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-firestore.js";

// Cấu hình Firebase thật của bạn
const firebaseConfig = {
  apiKey: "AIzaSyCW9wBtt0kMoccggxjzTn-aLW6-yxIXtV8",
  authDomain: "sola-tracker.firebaseapp.com",
  projectId: "sola-tracker",
  storageBucket: "sola-tracker.firebasestorage.app",
  messagingSenderId: "998620658014",
  appId: "1:998620658014:web:7fe8aa335332caa1b0f7cf"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
// Dữ liệu mẫu (Mock Data) hiển thị tạm thời nếu chưa có cấu hình Firebase
const MOCK_DATA = [
    {
        tower: "G1", area_m2: 32, layout: "Studio", direction: "ĐN", floor_band: "trung",
        price_bil: 1.85, payment_terms: "Thanh toán tiến độ", source: "facebook",
        url: "#", posted_at: new Date().toISOString()
    },
    {
        tower: "G3", area_m2: 43, layout: "1PN+", direction: "TB", floor_band: "cao",
        price_bil: 2.45, payment_terms: "Vay ngân hàng 70%", source: "batdongsan",
        url: "#", posted_at: new Date(Date.now() - 86400000).toISOString()
    },
    {
        tower: "G2", area_m2: 54, layout: "2PN", direction: "ĐB", floor_band: "thấp",
        price_bil: 3.10, payment_terms: "Thanh toán 95% nhận chiết khấu", source: "facebook",
        url: "#", posted_at: new Date(Date.now() - 172800000).toISOString()
    },
    {
        tower: "GS1", area_m2: 64, layout: "2PN+", direction: "TN", floor_band: "trung",
        price_bil: 3.80, payment_terms: "Ân hạn nợ gốc 24 tháng", source: "facebook",
        url: "#", posted_at: new Date(Date.now() - 259200000).toISOString()
    },
    {
        tower: "G1", area_m2: 75, layout: "3PN", direction: "ĐN", floor_band: "cao",
        price_bil: 4.50, payment_terms: "Thanh toán chuẩn", source: "batdongsan",
        url: "#", posted_at: new Date(Date.now() - 345600000).toISOString()
    }
];

let allListings = [];

// Khởi tạo Firebase nếu có config
let db = null;
if (firebaseConfig.apiKey) {
    const app = initializeApp(firebaseConfig);
    db = getFirestore(app);
}

// DOM Elements
const grid = document.getElementById('listingGrid');
const loading = document.getElementById('loading');
const resultCount = document.getElementById('resultCount');
const template = document.getElementById('cardTemplate');

// Filters
const filters = {
    tower: document.getElementById('towerFilter'),
    layout: document.getElementById('layoutFilter'),
    direction: document.getElementById('directionFilter'),
    sort: document.getElementById('priceSort')
};

// Khởi tạo ứng dụng
async function init() {
    try {
        if (db) {
            // Lấy dữ liệu thật từ Firestore
            const q = query(collection(db, "listings"), orderBy("posted_at", "desc"));
            const snapshot = await getDocs(q);
            allListings = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
        } else {
            // Dùng dữ liệu giả nếu chưa cài Firebase
            console.warn("Chưa cấu hình Firebase, đang hiển thị dữ liệu giả (Mock Data).");
            allListings = MOCK_DATA;
        }

        loading.classList.add('hidden');
        grid.classList.remove('hidden');
        
        applyFilters();
        
        // Gắn sự kiện cho các filter
        Object.values(filters).forEach(select => {
            select.addEventListener('change', applyFilters);
        });

    } catch (error) {
        console.error("Lỗi tải dữ liệu:", error);
        loading.innerHTML = `<p style="color: #ef4444;">Lỗi tải dữ liệu: ${error.message}</p>`;
    }
}

// Xử lý lọc dữ liệu
function applyFilters() {
    let filtered = [...allListings];

    const t = filters.tower.value;
    const l = filters.layout.value;
    const d = filters.direction.value;
    const s = filters.sort.value;

    if (t !== 'all') filtered = filtered.filter(x => x.tower === t);
    if (l !== 'all') filtered = filtered.filter(x => x.layout === l);
    if (d !== 'all') filtered = filtered.filter(x => x.direction === d);

    // Sắp xếp
    if (s === 'asc') filtered.sort((a, b) => (a.price_bil || 0) - (b.price_bil || 0));
    else if (s === 'desc') filtered.sort((a, b) => (b.price_bil || 0) - (a.price_bil || 0));
    else if (s === 'latest') filtered.sort((a, b) => new Date(b.posted_at) - new Date(a.posted_at));

    renderListings(filtered);
}

// Hiển thị danh sách ra màn hình
function renderListings(listings) {
    grid.innerHTML = '';
    resultCount.textContent = `Tìm thấy ${listings.length} căn hộ`;

    if (listings.length === 0) {
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: var(--text-secondary);">
            Không tìm thấy căn hộ nào phù hợp với bộ lọc.
        </div>`;
        return;
    }

    listings.forEach(item => {
        const clone = template.content.cloneNode(true);
        
        // Giá
        const priceStr = item.price_bil ? item.price_bil.toFixed(2) : "Thỏa thuận";
        clone.querySelector('.price-val').textContent = priceStr;
        if (!item.price_bil) clone.querySelector('.price-unit').style.display = 'none';

        // Thông tin cơ bản
        clone.querySelector('.layout-badge').textContent = item.layout || 'CXĐ';
        clone.querySelector('.tower-info').textContent = `Tòa ${item.tower || 'CXĐ'}`;
        
        // Specs
        clone.querySelector('.area-val').textContent = item.area_m2 ? `${item.area_m2} m²` : '--';
        clone.querySelector('.direction-val').textContent = item.direction || '--';
        clone.querySelector('.floor-val').textContent = `Tầng ${item.floor_band || item.floor_no || '--'}`;
        
        // Chính sách / Thanh toán
        clone.querySelector('.payment-terms').textContent = item.payment_terms || 'Không có thông tin chi tiết thanh toán/vay vốn.';
        
        // Meta data
        const dateObj = new Date(item.posted_at);
        const dateStr = isNaN(dateObj) ? 'Không rõ ngày' : dateObj.toLocaleDateString('vi-VN');
        clone.querySelector('.time-posted').textContent = dateStr;
        clone.querySelector('.source-tag').textContent = `Nguồn: ${item.source || 'ẩn'}`;
        
        // URL
        const btn = clone.querySelector('.view-btn');
        if (item.url) {
            btn.href = item.url;
        } else {
            btn.style.display = 'none';
        }

        grid.appendChild(clone);
    });
}

// Bắt đầu
document.addEventListener('DOMContentLoaded', init);
