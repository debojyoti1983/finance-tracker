// Auto-dismiss alerts after 4 seconds
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.alert-dismissible').forEach(el => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      if (bsAlert) bsAlert.close();
    }, 4000);
  });

  // Format INR input fields with comma display (visual only)
  document.querySelectorAll('input[type=number]').forEach(el => {
    el.addEventListener('wheel', e => e.preventDefault());
  });
});

// Global INR formatter
function fmtINR(n) {
  n = parseFloat(n) || 0;
  if (n >= 10000000) return '₹' + (n / 10000000).toFixed(2) + 'Cr';
  if (n >= 100000)   return '₹' + (n / 100000).toFixed(2) + 'L';
  return '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}
