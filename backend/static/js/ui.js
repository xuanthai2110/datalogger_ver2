let isSettingsOpen = false;

function initApp() {
    document.getElementById('login-view').classList.add('hidden');
    document.getElementById('app-view').classList.remove('hidden');
    showView('overview');
    
    // Tải trước cấu hình toàn cục ngay khi ứng dụng khởi chạy
    if (typeof loadSettings === 'function') {
        loadSettings().catch(err => console.error("Error loading settings in initApp:", err));
    }

    setInterval(() => { 
        document.getElementById('server-time').innerHTML = `<i class="fas fa-clock"></i> ${new Date().toLocaleTimeString('vi-VN')}`; 
    }, 1000);
    setInterval(() => { 
        if(document.getElementById('view-overview').classList.contains('hidden') === false) loadDashboard(); 
    }, 15000);
}

function toggleSettingsMenu() {
    const submenu = document.getElementById('settings-submenu');
    const arrow = document.querySelector('#menu-settings i.fa-chevron-down');
    
    if (isSettingsOpen) {
        submenu.style.display = 'none';
        if (arrow) arrow.style.transform = 'rotate(-90deg)';
    } else {
        submenu.style.display = 'block';
        if (arrow) arrow.style.transform = 'rotate(0deg)';
    }
    isSettingsOpen = !isSettingsOpen;
}

function showView(v) {
    console.log("Switching to view:", v);
    
    // Dọn dẹp timer đồng bộ khi chuyển sang view khác
    if (v !== 'sync') {
        if (typeof syncPollInterval !== 'undefined' && syncPollInterval) {
            clearInterval(syncPollInterval);
            syncPollInterval = null;
            console.log("Cleared sync poll interval.");
        }
    }
    
    const debug = document.getElementById('ui-debug');
    if (debug) debug.innerText = "View: " + v;
    
    // Ẩn tất cả các view section
    document.querySelectorAll('.view-section').forEach(s => s.classList.add('hidden'));
    
    // Hiện view section tương ứng
    const section = document.getElementById(`view-${v}`);
    if (section) {
        section.classList.remove('hidden');
    } else {
        console.error("View section not found for:", v);
    }
    
    // Reset trạng thái active của tất cả các menu sidebar và submenu
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.sub-item').forEach(i => i.classList.remove('active'));
    
    // Xử lý active menu cha / con dựa vào view
    const isSubmenuItem = ['plant', 'ip', 'rs485', 'ethernet', 'diboard', 'digitalsensor', 'status'].includes(v);
    
    if (isSubmenuItem) {
        // Active cho menu cha Settings
        document.getElementById('menu-settings').classList.add('active');
        // Mở accordion submenu nếu đang đóng
        const submenu = document.getElementById('settings-submenu');
        const arrow = document.querySelector('#menu-settings i.fa-chevron-down');
        submenu.style.display = 'block';
        if (arrow) arrow.style.transform = 'rotate(0deg)';
        isSettingsOpen = true;
        
        // Active cho mục con tương ứng
        const subItem = document.getElementById(`sub-${v}`);
        if (subItem) subItem.classList.add('active');
    } else {
        // Đóng và tắt active cho menu Settings nếu chọn menu chính khác
        const submenu = document.getElementById('settings-submenu');
        const arrow = document.querySelector('#menu-settings i.fa-chevron-down');
        submenu.style.display = 'none';
        if (arrow) arrow.style.transform = 'rotate(-90deg)';
        isSettingsOpen = false;
        
        // Active cho menu chính tương ứng
        const navItem = document.getElementById(`menu-${v}`);
        if (navItem) navItem.classList.add('active');
    }

    // Tải dữ liệu tương ứng cho view đó
    if (v === 'overview') { 
        loadDashboard(); 
    }
    else if (v === 'sync') { 
        console.log("Loading sync view data...");
        
        // Dọn dẹp timer cũ trước khi khởi tạo
        if (typeof syncPollInterval !== 'undefined' && syncPollInterval) {
            clearInterval(syncPollInterval);
            syncPollInterval = null;
        }

        if (typeof loadSync === 'function') {
             loadSync().catch(e => {
                 console.error("loadSync error:", e);
                 if (debug) debug.innerText += " ERR: " + e.message;
             });
        }

        // Thiết lập timer check 1p/lần
        if (typeof syncPollInterval !== 'undefined') {
            syncPollInterval = setInterval(async () => {
                console.log("Polling sync status from server...");
                if (typeof loadSync === 'function') {
                    await loadSync();
                    // Nếu người dùng đang chọn dự án nào đó, tự động load lại thông tin inverter
                    const select = document.getElementById('sync-project-select');
                    if (select && select.value && typeof loadSyncProjectDetails === 'function') {
                        await loadSyncProjectDetails();
                    }
                }
            }, 60000);
        }
    }
    else if (v === 'project-device') { 
        loadSettings(); 
        switchInnerTab('proj-tab');
    }
    else if (v === 'plant') {
        if (typeof loadPlantSettings === 'function') loadPlantSettings();
    }
    else if (v === 'ip') {
        if (typeof loadIPSettings === 'function') loadIPSettings();
    }
    else if (v === 'rs485') {
        loadSettings(); // Tải cấu hình truyền thông và bảng
    }
    else if (v === 'ethernet') {
        loadSettings(); // Tải cấu hình truyền thông và bảng
    }
    else if (v === 'diboard') {
        if (typeof loadDIBoardSettings === 'function') loadDIBoardSettings();
    }
    else if (v === 'digitalsensor') {
        if (typeof loadDigitalSensorSettings === 'function') loadDigitalSensorSettings();
    }
    else if (v === 'status') {
        if (typeof loadStatusSettings === 'function') loadStatusSettings();
    }
    else if (v === 'accounts') {
        loadAccounts();
    }
}

function switchInnerTab(tabId) {
    document.querySelectorAll('.inner-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.inner-tab-content').forEach(content => {
        content.classList.remove('active');
    });

    const activeTabButton = document.querySelector(`.inner-tab[onclick*="switchInnerTab('${tabId}')"]`);
    if (activeTabButton) activeTabButton.classList.add('active');
    
    const activeTabContent = document.getElementById(tabId);
    if (activeTabContent) activeTabContent.classList.add('active');
    
    if (tabId === 'evn-tab') {
        if (typeof loadEVNVPN === 'function') loadEVNVPN();
    }
    else if (tabId === 'ze-tab') {
        if (typeof initZeroExportTab === 'function') initZeroExportTab();
    }
}

function toggleCommFields() {
    const t = document.getElementById('comm-type-select').value;
    document.getElementById('fields-tcp').classList.toggle('hidden', t!=='TCP');
    document.getElementById('fields-rtu').classList.toggle('hidden', t!=='RTU');
}

// --- CUSTOM CONFIRM DIALOG MODAL ---
let confirmCallback = null;

function showConfirmModal(title, message, onConfirm) {
    const modal = document.getElementById('confirm-modal');
    if (!modal) return;
    document.getElementById('confirm-title').innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${title}`;
    document.getElementById('confirm-message').innerText = message;
    
    confirmCallback = onConfirm;
    modal.style.display = 'flex';
    
    const yesBtn = document.getElementById('confirm-yes-btn');
    yesBtn.onclick = function() {
        if (confirmCallback) {
            confirmCallback();
        }
        closeConfirmModal();
    };
}

function closeConfirmModal() {
    const modal = document.getElementById('confirm-modal');
    if (modal) {
        modal.style.display = 'none';
    }
    confirmCallback = null;
}

