let syncProjects = [];
let currentUser = null;
let syncPollInterval = null;

async function loadSync() {
    console.log("loadSync called");
    // 1. Get current user info (for role)
    currentUser = await apiCall('/auth/me');
    console.log("Current user for sync:", currentUser);
    if (!currentUser) {
        console.error("Failed to get current user info for sync");
        return;
    }

    // 2. Load projects
    const data = await apiCall('/projects');
    syncProjects = (data && data.projects) || [];

    const select = document.getElementById('sync-project-select');
    select.innerHTML = '<option value="">-- Chọn dự án --</option>' +
        syncProjects.map(p => `<option value="${p.id}">${p.name} (${p.sync_status || 'pending'})</option>`).join('');
}

async function loadSyncProjectDetails() {
    const projId = document.getElementById('sync-project-select').value;
    const detailsDiv = document.getElementById('sync-details');
    const msg = document.getElementById('sync-status-msg');
    msg.innerText = "";

    if (!projId) {
        detailsDiv.classList.add('hidden');
        return;
    }

    const project = syncProjects.find(p => String(p.id) === String(projId));
    if (!project) return;

    // Fetch inverters for this project
    const inverters = await apiCall('/inverters'); // This gets ALL, filter locally or update API
    const projectInverters = (inverters || []).filter(inv => String(inv.project_id) === String(projId));

    const tbody = document.getElementById('sync-inverters-body');
    tbody.innerHTML = projectInverters.map(inv => {
        const isApproved = inv.sync_status === 'approved';
        return `
        <tr>
            <td>${inv.serial_number}</td>
            <td>${inv.model}</td>
            <td><span class="badge ${isApproved ? 'success' : 'warning'}">${inv.sync_status || 'pending'}</span></td>
            <td>${inv.server_id ? 'ID: ' + inv.server_id : (inv.server_request_id ? 'Req: ' + inv.server_request_id : '-')}</td>
            <td>
                <div style="display:flex; gap: 5px;">
                    <button class="action-btn" style="color:var(--success); ${isApproved ? 'display:none' : ''}" onclick="handleInverterSync(${inv.id})" title="Create"><i class="fas fa-plus"></i></button>
                    <button class="action-btn" style="color:var(--warning); ${isApproved ? '' : 'display:none'}" onclick="handleInverterSync(${inv.id})" title="Update"><i class="fas fa-edit"></i></button>
                    <button class="action-btn delete" onclick="handleDeleteSync('inverter', ${inv.id})" title="Delete"><i class="fas fa-trash"></i></button>
                </div>
            </td>
        </tr>
    `}).join('');

    // Fetch batteries for this project
    const batteries = await apiCall('/batteries');
    const projectBatteries = (batteries || []).filter(b => String(b.project_id) === String(projId));

    const battTbody = document.getElementById('sync-batteries-body');
    if (battTbody) {
        if (projectBatteries.length === 0) {
            battTbody.innerHTML = '<tr><td colspan="5" style="text-align:center; opacity:0.5;">Dự án này chưa có Pin lưu trữ nào.</td></tr>';
        } else {
            battTbody.innerHTML = projectBatteries.map(b => {
                const isApproved = b.sync_status === 'approved';
                return `
                <tr>
                    <td>${b.serial_number}</td>
                    <td><strong>${b.brand}</strong> - ${b.model}</td>
                    <td><span class="badge ${isApproved ? 'success' : 'warning'}">${b.sync_status || 'pending'}</span></td>
                    <td>${b.server_id ? 'ID: ' + b.server_id : (b.server_request_id ? 'Req: ' + b.server_request_id : '-')}</td>
                    <td>
                        <div style="display:flex; gap: 5px;">
                            <button class="action-btn" style="color:var(--success); ${isApproved ? 'display:none' : ''}" onclick="handleBatterySync(${b.id})" title="Create"><i class="fas fa-plus"></i></button>
                            <button class="action-btn" style="color:var(--warning); ${isApproved ? '' : 'display:none'}" onclick="handleBatterySync(${b.id})" title="Update"><i class="fas fa-edit"></i></button>
                            <button class="action-btn delete" onclick="handleDeleteSync('battery', ${b.id})" title="Delete"><i class="fas fa-trash"></i></button>
                        </div>
                    </td>
                </tr>
                `;
            }).join('');
        }
    }

    // Cấu hình nút bấm cho Project
    const isProjectApproved = project.sync_status === 'approved';
    const btnCreate = document.getElementById('btn-sync-create');
    const btnUpdate = document.getElementById('btn-sync-update');

    if (isProjectApproved) {
        btnCreate.style.display = 'none';
        btnUpdate.style.display = 'inline-block';
    } else {
        btnCreate.style.display = 'inline-block';
        btnUpdate.style.display = 'none';
    }

    detailsDiv.classList.remove('hidden');
}

async function handleSync() {
    const projId = document.getElementById('sync-project-select').value;
    if (!projId) return;

    const msg = document.getElementById('sync-status-msg');
    const btn = document.getElementById('btn-sync-create') || document.getElementById('btn-sync-update');

    msg.innerText = "Đang xử lý đồng bộ...";
    msg.className = "text-primary";
    if (btn) btn.disabled = true;

    try {
        const res = await apiCall(`/sync/project/${projId}`, 'POST');
        if (res && res.ok) {
            msg.innerText = res.message || "Đồng bộ thành công!";
            msg.className = "text-success";
            alert(res.message);
            loadSync();
            loadSyncProjectDetails();
        } else {
            msg.innerText = "Đồng bộ thất bại: " + (res ? res.detail : "Lỗi không xác định");
            msg.className = "text-danger";
        }
    } catch (e) {
        msg.innerText = "Lỗi kết nối: " + e.message;
        msg.className = "text-danger";
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function handleInverterSync(invId) {
    const msg = document.getElementById('sync-status-msg');
    msg.innerText = `Đang đồng bộ biến tần ${invId}...`;
    msg.className = "text-primary";

    try {
        const res = await apiCall(`/sync/inverter/${invId}`, 'POST');
        if (res && res.ok) {
            msg.innerText = res.message || "Đồng bộ biến tần thành công!";
            msg.className = "text-success";
            loadSyncProjectDetails();
        } else {
            msg.innerText = "Lỗi đồng bộ biến tần: " + (res ? res.detail : "Lỗi không xác định");
            msg.className = "text-danger";
        }
    } catch (e) {
        msg.innerText = "Lỗi kết nối: " + e.message;
        msg.className = "text-danger";
    }
}

async function handleBatterySync(battId) {
    const msg = document.getElementById('sync-status-msg');
    msg.innerText = `Đang đồng bộ Pin lưu trữ ${battId}...`;
    msg.className = "text-primary";

    try {
        const res = await apiCall(`/sync/battery/${battId}`, 'POST');
        if (res && res.ok) {
            msg.innerText = res.message || "Đồng bộ Pin lưu trữ thành công!";
            msg.className = "text-success";
            loadSyncProjectDetails();
        } else {
            msg.innerText = "Lỗi đồng bộ Pin: " + (res ? res.detail : "Lỗi không xác định");
            msg.className = "text-danger";
        }
    } catch (e) {
        msg.innerText = "Lỗi kết nối: " + e.message;
        msg.className = "text-danger";
    }
}

async function handleDeleteSync(type, id = null) {
    const msg = document.getElementById('sync-status-msg');
    let endpoint = `/sync/project/${document.getElementById('sync-project-select').value}/delete`;
    if (type === 'inverter') endpoint = `/sync/inverter/${id}/delete`;
    if (type === 'battery') endpoint = `/sync/battery/${id}/delete`;

    if (!confirm(`Bạn có chắc chắn muốn gửi yêu cầu XÓA ${type} này lên server không?`)) return;

    msg.innerText = `Đang gửi yêu cầu xóa ${type}...`;
    msg.className = "text-primary";

    try {
        const res = await apiCall(endpoint, 'POST');
        if (res && res.ok) {
            msg.innerText = res.message || `Đã gửi yêu cầu xóa ${type}!`;
            msg.className = "text-success";
            loadSyncProjectDetails();
        } else {
            msg.innerText = `Lỗi xóa ${type}: ` + (res ? res.detail : "Lỗi không xác định");
            msg.className = "text-danger";
        }
    } catch (e) {
        msg.innerText = "Lỗi kết nối: " + e.message;
        msg.className = "text-danger";
    }
}
