// Animate buttons on hover
document.addEventListener('DOMContentLoaded', function() {
    // Add loading animation
    document.body.classList.add('loaded');

    // Initialize counters if on dashboard page
    if (document.getElementById('parkingSlots')) {
        updateCounters();
    }
    
    // Initialize form animations
    initFormAnimations();
    
    // Initialize confirmation dialogs
    initConfirmationDialogs();

    // Initialize WebSocket connections for notifications
    initNotifications();
});

// Function to update counters on dashboard
function updateCounters() {
    const slots = document.querySelectorAll('.slot');
    let emptyCount = 0;
    let occupiedCount = 0;
    let reservedCount = 0;

    slots.forEach(slot => {
        if (slot.classList.contains('empty')) emptyCount++;
        if (slot.classList.contains('occupied')) occupiedCount++;
        if (slot.classList.contains('reserved')) reservedCount++;
    });

    // Update counter elements if they exist
    if (document.getElementById('empty-count'))
        document.getElementById('empty-count').textContent = emptyCount;
    if (document.getElementById('occupied-count'))
        document.getElementById('occupied-count').textContent = occupiedCount;
    if (document.getElementById('reserved-count'))
        document.getElementById('reserved-count').textContent = reservedCount;
}

// Initialize form animations
function initFormAnimations() {
    // Button hover animation
    const buttons = document.querySelectorAll('button, .btn-sm, .btn-login, .btn-reserve, .btn-cancel');
    buttons.forEach(button => {
        if (!button.disabled) {
            button.addEventListener('mouseenter', function() {
                this.style.transform = 'translateY(-3px)';
                this.style.boxShadow = '0 5px 15px rgba(0, 0, 0, 0.3)';
            });

            button.addEventListener('mouseleave', function() {
                this.style.transform = '';
                this.style.boxShadow = '';
            });
        }
    });

    // Handle form submission with animation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // Check if form has a specific class to prevent animation
            if (this.classList.contains('no-animation')) return;
            
            const button = this.querySelector('button[type="submit"]');
            if (button) {
                // Store original content
                if (!button.dataset.originalContent) {
                    button.dataset.originalContent = button.innerHTML;
                }
                button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
                button.disabled = true;
                
                // Enable button after 10 seconds in case of issues
                setTimeout(() => {
                    if (button.disabled) {
                        button.disabled = false;
                        button.innerHTML = button.dataset.originalContent;
                    }
                }, 10000);
            }
        });
    });
}

// Initialize confirmation dialogs
function initConfirmationDialogs() {
    const deleteUserForms = document.querySelectorAll('form[action*="delete_user"]');
    deleteUserForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
                e.preventDefault();
            }
        });
    });
    
    const cancelReservationForms = document.querySelectorAll('form[action*="cancel_reservation"]');
    cancelReservationForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!confirm('Are you sure you want to cancel this reservation?')) {
                e.preventDefault();
            }
        });
    });
}

// Initialize WebSocket notifications
function initNotifications() {
    // Check if we're on a page that should have notifications
    const userId = document.body.dataset.userId;
    if (!userId) return;

    // Connect to WebSocket server if it's not already defined in the page
    if (typeof socket === 'undefined') {
        var socket = io();
        
        // Join user-specific room for notifications
        socket.emit('join', { room: 'user_' + userId });
        
        // Listen for new notifications
        socket.on('new_notification', function(data) {
            showNotificationPopup(data.message);
            updateNotificationBadge();
            
            // Reload page after a delay if we're on the dashboard
            if (window.location.pathname === '/dashboard') {
                setTimeout(function() {
                    location.reload();
                }, 5000);
            }
        });
    }
}

// Function to handle real-time slot updates
function updateParkingSlots(slots) {
    let emptyCount = 0;
    let occupiedCount = 0;
    let reservedCount = 0;

    // Update the UI with new parking data
    for (let i = 0; i < slots.length; i++) {
        let slot = slots[i];
        let slotElement = document.getElementById('slot-' + slot.id);

        if (!slotElement) continue;

        // Reset classes
        slotElement.classList.remove('empty', 'occupied', 'reserved');

        // Add appropriate class and icon
        let iconElement = slotElement.querySelector('.slot-icon i');
        let statusText = slotElement.querySelector('.status-text');

        if (slot.status === 0) {
            slotElement.classList.add('empty');
            if (statusText) statusText.textContent = 'Empty';
            if (iconElement) iconElement.className = 'fas fa-parking';
            emptyCount++;
        } else if (slot.status === 1) {
            slotElement.classList.add('occupied');
            if (statusText) statusText.textContent = 'Occupied';
            if (iconElement) iconElement.className = 'fas fa-car';
            occupiedCount++;
        } else if (slot.status === 2) {
            slotElement.classList.add('reserved');
            if (statusText) statusText.textContent = 'Reserved';
            if (iconElement) iconElement.className = 'fas fa-bookmark';
            reservedCount++;
        }
    }

    // Update counters
    if (document.getElementById('empty-count'))
        document.getElementById('empty-count').textContent = emptyCount;
    if (document.getElementById('occupied-count'))
        document.getElementById('occupied-count').textContent = occupiedCount;
    if (document.getElementById('reserved-count'))
        document.getElementById('reserved-count').textContent = reservedCount;

    // Update the select dropdown options for reservation
    let select = document.getElementById('slot_id');
    if (select) {
        // Store current selection if any
        let currentSelection = select.value;
        select.innerHTML = '';

        let availableSlots = 0;
        for (let i = 0; i < slots.length; i++) {
            if (slots[i].status === 0) {
                availableSlots++;
                let option = document.createElement('option');
                option.value = slots[i].id;
                option.textContent = 'Slot ' + (slots[i].id + 1);
                
                // Restore previous selection if it's still available
                if (slots[i].id.toString() === currentSelection) {
                    option.selected = true;
                }
                
                select.appendChild(option);
            }
        }
        
        // If no slots available, disable form
        const reserveForm = document.getElementById('reserveForm');
        if (reserveForm) {
            const reserveBtn = reserveForm.querySelector('.btn-reserve');
            
            if (availableSlots === 0) {
                select.innerHTML = '<option value="">No slots available</option>';
                if (reserveBtn) {
                    reserveBtn.disabled = true;
                    reserveBtn.innerHTML = '<span>No Available Slots</span> <i class="fas fa-times-circle"></i>';
                }
            } else {
                if (reserveBtn) {
                    reserveBtn.disabled = false;
                    reserveBtn.innerHTML = '<span>Reserve Now</span> <i class="fas fa-check-circle"></i>';
                }
            }
        }
    }

    // Flash animation for the update indicator
    let updateIcon = document.querySelector('.update-status i');
    if (updateIcon) {
        updateIcon.classList.add('flash');
        setTimeout(() => {
            updateIcon.classList.remove('flash');
        }, 1000);
    }
}

// Add loading indicator for page transitions
(function() {
    const links = document.querySelectorAll('a:not([target="_blank"]):not([href^="#"]):not([href^="javascript"])');
    links.forEach(link => {
        link.addEventListener('click', function(e) {
            // Don't add loading for anchor links or javascript actions
            if (this.getAttribute('href').startsWith('#') || 
                this.getAttribute('href').startsWith('javascript:')) {
                return;
            }
            
            // Create loading overlay
            const loadingOverlay = document.createElement('div');
            loadingOverlay.className = 'loading-overlay';
            loadingOverlay.innerHTML = `
                <div class="loading-spinner">
                    <i class="fas fa-car fa-spin"></i>
                    <p>Loading...</p>
                </div>
            `;
            
            // Add overlay to body
            document.body.appendChild(loadingOverlay);
            
            // Add styles if they don't exist
            if (!document.getElementById('loading-styles')) {
                const styles = document.createElement('style');
                styles.id = 'loading-styles';
                styles.textContent = `
                    .loading-overlay {
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background-color: rgba(0, 0, 0, 0.7);
                        backdrop-filter: blur(5px);
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        z-index: 9999;
                        animation: fadeIn 0.2s ease;
                    }
                    .loading-spinner {
                        text-align: center;
                    }
                    .loading-spinner i {
                        font-size: 3rem;
                        color: var(--primary-light);
                        margin-bottom: 1rem;
                    }
                    .loading-spinner p {
                        color: white;
                        font-size: 1.2rem;
                    }
                `;
                document.head.appendChild(styles);
            }
            
            // Remove overlay after 10 seconds in case of page load issues
            setTimeout(() => {
                if (document.querySelector('.loading-overlay')) {
                    document.querySelector('.loading-overlay').remove();
                }
            }, 10000);
        });
    });
})();

// Show notification popup
function showNotificationPopup(message) {
    // Create popup element
    var popup = document.createElement('div');
    popup.className = 'notification-popup';
    
    // Create content
    popup.innerHTML = `
        <div class="notification-popup-header">
            <i class="fas fa-bell"></i>
            <span>New Notification</span>
            <button class="notification-close"><i class="fas fa-times"></i></button>
        </div>
        <div class="notification-popup-content">
            <p>${message}</p>
        </div>
    `;
    
    // Add to body
    document.body.appendChild(popup);
    
    // Add animation class
    setTimeout(function() {
        popup.classList.add('show');
    }, 100);
    
    // Add close functionality
    popup.querySelector('.notification-close').addEventListener('click', function() {
        popup.classList.remove('show');
        setTimeout(function() {
            popup.remove();
        }, 300);
    });
    
    // Auto close after 10 seconds
    setTimeout(function() {
        if (popup.parentNode) {
            popup.classList.remove('show');
            setTimeout(function() {
                if (popup.parentNode) {
                    popup.remove();
                }
            }, 300);
        }
    }, 10000);
    
    // Play notification sound if available
    var notificationSound = document.getElementById('notification-sound');
    if (notificationSound) {
        notificationSound.play().catch(function(error) {
            // Ignore autoplay errors - happens in browsers with strict autoplay policies
            console.log("Audio play failed:", error);
        });
    }
}

// Update notification badge
function updateNotificationBadge() {
    var badgeElement = document.querySelector('.notification-badge');
    if (badgeElement) {
        var count = parseInt(badgeElement.textContent || "0");
        badgeElement.textContent = count + 1;
        badgeElement.style.display = 'inline-block';
    } else {
        // Create new badge if it doesn't exist
        var navLink = document.querySelector('a[href*="notifications"]');
        if (navLink) {
            var badge = document.createElement('span');
            badge.className = 'notification-badge';
            badge.textContent = '1';
            navLink.appendChild(badge);
        }
    }
}

// Enable tooltip functionality
function enableTooltips() {
    const tooltips = document.querySelectorAll('[data-tooltip]');
    
    tooltips.forEach(tooltip => {
        tooltip.addEventListener('mouseenter', function() {
            const text = this.getAttribute('data-tooltip');
            
            // Create tooltip element
            const tooltipEl = document.createElement('div');
            tooltipEl.className = 'tooltip';
            tooltipEl.textContent = text;
            
            // Position relative to trigger
            const rect = this.getBoundingClientRect();
            tooltipEl.style.top = `${rect.top - 30}px`;
            tooltipEl.style.left = `${rect.left + (rect.width / 2)}px`;
            
            // Add to body
            document.body.appendChild(tooltipEl);
            
            // Add styles if needed
            if (!document.getElementById('tooltip-styles')) {
                const styles = document.createElement('style');
                styles.id = 'tooltip-styles';
                styles.textContent = `
                    .tooltip {
                        position: fixed;
                        transform: translateX(-50%);
                        background-color: rgba(0, 0, 0, 0.8);
                        color: white;
                        padding: 0.5rem 0.8rem;
                        border-radius: 4px;
                        font-size: 0.8rem;
                        z-index: 1000;
                        pointer-events: none;
                        animation: fadeIn 0.2s ease;
                    }
                    .tooltip::after {
                        content: '';
                        position: absolute;
                        top: 100%;
                        left: 50%;
                        transform: translateX(-50%);
                        border-width: 5px;
                        border-style: solid;
                        border-color: rgba(0, 0, 0, 0.8) transparent transparent transparent;
                    }
                `;
                document.head.appendChild(styles);
            }
        });
        
        tooltip.addEventListener('mouseleave', function() {
            const tooltipEl = document.querySelector('.tooltip');
            if (tooltipEl) {
                tooltipEl.remove();
            }
        });
    });
}

// Call enableTooltips on DOMContentLoaded
document.addEventListener('DOMContentLoaded', enableTooltips);
