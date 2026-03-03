class EmailProcessorAdmin {
    constructor() {
        this.apiBase = '/api/v1';
        this.init();
    }

    async init() {
        await this.checkConnection();
        await this.loadStatistics();
        this.setupEventListeners();
        await this.loadObjects();
        await this.loadEmailSources();
        await this.loadDocuments();
        await this.loadReports();
        
        // Автообновление статистики каждые 30 секунд
        setInterval(() => this.loadStatistics(), 30000);
    }

    async checkConnection() {
        try {
            const response = await fetch(`${this.apiBase}/health`);
            const statusEl = document.getElementById('connection-status');
            if (response.ok) {
                statusEl.innerHTML = '<i class="bi bi-circle-fill text-success"></i> Подключено';
            } else {
                statusEl.innerHTML = '<i class="bi bi-circle-fill text-danger"></i> Ошибка соединения';
            }
        } catch (error) {
            document.getElementById('connection-status').innerHTML = 
                '<i class="bi bi-circle-fill text-danger"></i> Нет соединения';
        }
    }

    async apiCall(endpoint, options = {}) {
        try {
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            
            if (!response.ok) {
                let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                
                try {
                    const errorData = await response.json();
                    if (errorData.detail) {
                        if (Array.isArray(errorData.detail)) {
                            // Pydantic validation errors
                            errorMessage = errorData.detail.map(err => err.msg || err).join(', ');
                        } else if (typeof errorData.detail === 'string') {
                            errorMessage = errorData.detail;
                        }
                    }
                } catch (e) {
                    // Ignore JSON parsing errors
                }
                
                throw new Error(errorMessage);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`API Error: ${endpoint}`, error);
            // Don't show alert here, let the caller handle it
            throw error;
        }
    }

    showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.querySelector('.container').insertBefore(alertDiv, document.querySelector('.container').firstChild);
        
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }

    async loadStatistics() {
        try {
            const stats = await this.apiCall('/reports/summary');
            document.getElementById('total-attachments').textContent = stats.total_attachments;
            document.getElementById('processed-attachments').textContent = stats.processed;
            document.getElementById('rejected-attachments').textContent = stats.rejected;
            document.getElementById('sent-attachments').textContent = stats.sent;
        } catch (error) {
            console.error('Failed to load statistics:', error);
        }
    }

    async loadObjects() {
        try {
            const objects = await this.apiCall('/objects/');
            const tbody = document.querySelector('#objects-table tbody');
            tbody.innerHTML = '';
            
            objects.forEach(obj => {
                const row = tbody.insertRow();
                row.innerHTML = `
                    <td>${obj.name}</td>
                    <td>${obj.calculator_number || '-'}</td>
                    <td>${obj.address || '-'}</td>
                    <td>${obj.email || '-'}</td>
                    <td><span class="badge bg-${obj.is_active ? 'success' : 'secondary'}">${obj.is_active ? 'Активен' : 'Неактивен'}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="admin.editObject('${obj.id}')">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="admin.deleteObject('${obj.id}')">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                `;
            });
        } catch (error) {
            console.error('Failed to load objects:', error);
        }
    }

    async loadEmailSources() {
        try {
            const sources = await this.apiCall('/email-sources/');
            const tbody = document.querySelector('#email-sources-table tbody');
            tbody.innerHTML = '';
            
            sources.forEach(source => {
                const row = tbody.insertRow();
                row.innerHTML = `
                    <td>${source.email}</td>
                    <td>${source.name || '-'}</td>
                    <td><span class="badge bg-${source.is_active ? 'success' : 'secondary'}">${source.is_active ? 'Активен' : 'Неактивен'}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="admin.editEmailSource('${source.id}')">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="admin.deleteEmailSource('${source.id}')">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                `;
            });
        } catch (error) {
            console.error('Failed to load email sources:', error);
        }
    }

    async loadDocuments(statusFilter = '') {
        try {
            let endpoint = '/attachments';
            if (statusFilter) {
                endpoint += `?status=${statusFilter}`;
            }
            
            const attachments = await this.apiCall(endpoint);
            const tbody = document.querySelector('#documents-table tbody');
            tbody.innerHTML = '';
            
            attachments.forEach(att => {
                const row = tbody.insertRow();
                const statusBadge = this.getStatusBadge(att.status);
                
                row.innerHTML = `
                    <td>${att.filename}</td>
                    <td>${att.calculator_number || '-'}</td>
                    <td>${att.object ? att.object.name : '-'}</td>
                    <td>${att.message ? att.message.from_email : '-'}</td>
                    <td>${statusBadge}</td>
                    <td>${att.reject_reason || '-'}</td>
                    <td>${new Date(att.created_at).toLocaleString()}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-info" onclick="admin.showAttachmentDetails('${att.id}')">
                            <i class="bi bi-eye"></i>
                        </button>
                        ${att.status === 'rejected' ? 
                            `<button class="btn btn-sm btn-outline-warning" onclick="admin.reprocessAttachment('${att.id}')">
                                <i class="bi bi-arrow-clockwise"></i>
                            </button>` : ''}
                        ${att.status === 'validated' ? 
                            `<button class="btn btn-sm btn-outline-success" onclick="admin.resendAttachment('${att.id}')">
                                <i class="bi bi-send"></i>
                            </button>` : ''}
                    </td>
                `;
            });
        } catch (error) {
            console.error('Failed to load documents:', error);
        }
    }

    async loadReports() {
        try {
            const rejections = await this.apiCall('/reports/rejections');
            const tbody = document.querySelector('#rejections-table tbody');
            tbody.innerHTML = '';
            
            rejections.forEach(rej => {
                const row = tbody.insertRow();
                row.innerHTML = `
                    <td>${rej.filename}</td>
                    <td><span class="badge bg-danger">${rej.reject_reason}</span></td>
                    <td>${rej.object_name || '-'}</td>
                    <td>${rej.message_subject || '-'}</td>
                    <td>${rej.from_email || '-'}</td>
                    <td>${new Date(rej.created_at).toLocaleString()}</td>
                `;
            });
        } catch (error) {
            console.error('Failed to load reports:', error);
        }
    }

    getStatusBadge(status) {
        const badges = {
            'new': 'secondary',
            'processing': 'warning',
            'validated': 'info',
            'sent': 'success',
            'rejected': 'danger'
        };
        const labels = {
            'new': 'Новый',
            'processing': 'В обработке',
            'validated': 'Проверен',
            'sent': 'Отправлен',
            'rejected': 'Отклонен'
        };
        const color = badges[status] || 'secondary';
        const label = labels[status] || status;
        return `<span class="badge bg-${color}">${label}</span>`;
    }

    setupEventListeners() {
        // Сброс формы при закрытии модалки
        document.getElementById('objectModal').addEventListener('hidden.bs.modal', () => {
            const form = document.getElementById('object-form');
            form.reset();
            form.removeAttribute('data-mode');
            form.removeAttribute('data-object-id');
        });

        // Сохранение объекта
        document.getElementById('save-object').addEventListener('click', async () => {
            const form = document.getElementById('object-form');
            const mode = form.getAttribute('data-mode');
            const objectId = form.getAttribute('data-object-id');
            const formData = new FormData(form);
            
            const data = {
                name: formData.get('name'),
                calculator_number: formData.get('calculator_number') || null,
                address: formData.get('address') || null,
                email: formData.get('email') || null
            };
            
            try {
                if (mode === 'edit' && objectId) {
                    // Редактирование
                    await this.apiCall(`/objects/${objectId}`, {
                        method: 'PUT',
                        body: JSON.stringify(data)
                    });
                    this.showAlert('Объект обновлен', 'success');
                } else {
                    // Создание нового
                    await this.apiCall('/objects/', {
                        method: 'POST',
                        body: JSON.stringify(data)
                    });
                    this.showAlert('Объект успешно добавлен', 'success');
                }
                
                bootstrap.Modal.getInstance(document.getElementById('objectModal')).hide();
                form.reset();
                form.removeAttribute('data-mode');
                form.removeAttribute('data-object-id');
                await this.loadObjects();
            } catch (error) {
                this.showAlert(`Ошибка при ${mode === 'edit' ? 'обновлении' : 'добавлении'} объекта`, 'danger');
            }
        });

        // Сохранение email источника
        document.getElementById('save-email-source').addEventListener('click', async () => {
            const form = document.getElementById('email-source-form');
            const formData = new FormData(form);
            
            const data = {
                email: formData.get('email'),
                name: formData.get('name') || null
            };
            
            try {
                await this.apiCall('/email-sources/', {
                    method: 'POST',
                    body: JSON.stringify(data)
                });
                
                bootstrap.Modal.getInstance(document.getElementById('email-source-modal')).hide();
                form.reset();
                await this.loadEmailSources();
                this.showAlert('Email источник успешно добавлен', 'success');
            } catch (error) {
                // Показываем детальное сообщение об ошибке
                let errorMessage = 'Ошибка при добавлении email источника';
                
                if (error.message.includes('HTTP 400')) {
                    errorMessage = 'Неверный формат email адреса';
                } else if (error.message.includes('already exists')) {
                    errorMessage = 'Такой email уже существует';
                } else if (error.message.includes('value is not a valid email')) {
                    errorMessage = 'Введите корректный email адрес';
                }
                
                this.showAlert(errorMessage, 'danger');
            }
        });

        // Фильтр документов
        document.getElementById('status-filter').addEventListener('change', (e) => {
            this.loadDocuments(e.target.value);
        });

        // Кнопки обновления
        document.getElementById('refresh-documents').addEventListener('click', () => {
            this.loadDocuments(document.getElementById('status-filter').value);
        });

        document.getElementById('refresh-reports').addEventListener('click', () => {
            this.loadReports();
        });
    }

    async deleteObject(id) {
        if (!confirm('Удалить этот объект?')) return;
        
        try {
            await this.apiCall(`/objects/${id}`, { method: 'DELETE' });
            await this.loadObjects();
            this.showAlert('Объект удален', 'success');
        } catch (error) {
            this.showAlert('Ошибка при удалении объекта', 'danger');
        }
    }

    async editObject(id) {
        try {
            const obj = await this.apiCall(`/objects/${id}`);
            
            const form = document.getElementById('object-form');
            form.reset();
            
            // Устанавливаем режим редактирования
            form.setAttribute('data-mode', 'edit');
            form.setAttribute('data-object-id', id);
            
            form.querySelector('input[name="name"]').value = obj.name;
            form.querySelector('input[name="calculator_number"]').value = obj.calculator_number || '';
            form.querySelector('input[name="address"]').value = obj.address || '';
            form.querySelector('input[name="email"]').value = obj.email || '';
            
            const modalEl = document.getElementById('objectModal');
            const modal = new bootstrap.Modal(modalEl);
            modal.show();
        } catch (error) {
            this.showAlert('Ошибка при загрузке объекта', 'danger');
        }
    }

    async deleteEmailSource(id) {
        if (!confirm('Удалить этот email источник?')) return;
        
        try {
            await this.apiCall(`/email-sources/${id}`, { method: 'DELETE' });
            await this.loadEmailSources();
            this.showAlert('Email источник удален', 'success');
        } catch (error) {
            this.showAlert('Ошибка при удалении email источника', 'danger');
        }
    }

    async editEmailSource(id) {
        try {
            const source = await this.apiCall(`/email-sources/${id}`);
            
            const form = document.getElementById('email-source-form');
            form.reset();
            
            form.querySelector('input[name="email"]').value = source.email;
            form.querySelector('input[name="name"]').value = source.name || '';
            
            const modalEl = document.getElementById('email-source-modal');
            const modal = new bootstrap.Modal(modalEl);
            modal.show();
            
            const saveBtn = document.getElementById('save-email-source');
            saveBtn.onclick = async () => {
                const data = {
                    email: form.querySelector('input[name="email"]').value,
                    name: form.querySelector('input[name="name"]').value || null
                };
                
                try {
                    await this.apiCall(`/email-sources/${id}`, {
                        method: 'PUT',
                        body: JSON.stringify(data)
                    });
                    
                    modal.hide();
                    await this.loadEmailSources();
                    this.showAlert('Email источник обновлен', 'success');
                } catch (error) {
                    this.showAlert('Ошибка при обновлении email источника', 'danger');
                }
            };
        } catch (error) {
            this.showAlert('Ошибка при загрузке email источника', 'danger');
        }
    }

    async reprocessAttachment(id) {
        try {
            await this.apiCall(`/attachments/${id}/reprocess`, { method: 'POST' });
            this.showAlert('Переобработка запущена', 'success');
            setTimeout(() => this.loadDocuments(), 2000);
        } catch (error) {
            this.showAlert('Ошибка при запуске переобработки', 'danger');
        }
    }

    async resendAttachment(id) {
        try {
            await this.apiCall(`/attachments/${id}/resend`, { method: 'POST' });
            this.showAlert('Повторная отправка запущена', 'success');
            setTimeout(() => this.loadDocuments(), 2000);
        } catch (error) {
            this.showAlert('Ошибка при запуске повторной отправки', 'danger');
        }
    }

    async showAttachmentDetails(id) {
        try {
            const details = await this.apiCall(`/attachments/${id}/details`);
            
            let html = `
                <h6>Детали вложения</h6>
                <p><strong>Файл:</strong> ${details.filename}</p>
                <p><strong>Размер:</strong> ${details.file_size ? `${details.file_size} байт` : '-'}</p>
                <p><strong>Статус:</strong> ${this.getStatusBadge(details.status)}</p>
            `;
            
            if (details.reject_reason) {
                html += `<p><strong>Причина отказа:</strong> ${details.reject_reason}</p>`;
            }
            
            if (details.message) {
                html += `
                    <h6>Сообщение</h6>
                    <p><strong>От:</strong> ${details.message.from_email}</p>
                    <p><strong>Тема:</strong> ${details.message.subject || '-'}</p>
                `;
            }
            
            if (details.validation_result) {
                html += `
                    <h6>Результат проверки</h6>
                    <pre class="bg-light p-2">${JSON.stringify(details.validation_result, null, 2)}</pre>
                `;
            }
            
            // Создаем модальное окно
            const modalDiv = document.createElement('div');
            modalDiv.className = 'modal fade';
            modalDiv.innerHTML = `
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Детали вложения</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            ${html}
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Закрыть</button>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modalDiv);
            const modal = new bootstrap.Modal(modalDiv);
            modal.show();
            
            modalDiv.addEventListener('hidden.bs.modal', () => {
                modalDiv.remove();
            });
            
        } catch (error) {
            this.showAlert('Ошибка при загрузке деталей вложения', 'danger');
        }
    }
}

// Инициализация приложения
const admin = new EmailProcessorAdmin();