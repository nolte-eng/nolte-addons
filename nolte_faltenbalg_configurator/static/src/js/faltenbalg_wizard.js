(function () {
    function updateChoiceCards(root) {
        root.querySelectorAll('.fb-choice-card').forEach(function (card) {
            var input = card.querySelector('input[type="radio"]');
            card.classList.toggle('is-selected', !!(input && input.checked));
            card.setAttribute('aria-pressed', input && input.checked ? 'true' : 'false');
        });
    }

    function isStepValid(stepEl) {
        var fields = stepEl.querySelectorAll('input, select, textarea');
        for (var i = 0; i < fields.length; i++) {
            var field = fields[i];
            if (field.type === 'hidden' || field.disabled || field.closest('.d-none')) {
                continue;
            }
            if (!field.checkValidity()) {
                field.reportValidity();
                return false;
            }
        }
        return true;
    }

    function bindChoiceCards(form, onChange) {
        form.querySelectorAll('.fb-choice-card').forEach(function (card) {
            card.setAttribute('tabindex', '0');
            card.setAttribute('role', 'button');
            var selectCard = function () {
                var input = card.querySelector('input[type="radio"]');
                if (!input) return;
                form.querySelectorAll('input[name="' + input.name + '"]').forEach(function (radio) { radio.checked = false; });
                input.checked = true;
                input.dispatchEvent(new Event('change', { bubbles: true }));
                updateChoiceCards(form);
                if (onChange) onChange(input.value);
            };
            card.addEventListener('click', function (ev) { ev.preventDefault(); ev.stopPropagation(); selectCard(); });
            card.addEventListener('keydown', function (ev) {
                if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); selectCard(); }
            });
        });
        form.querySelectorAll('.fb-choice-card input[type="radio"]').forEach(function (radio) {
            radio.addEventListener('change', function () {
                updateChoiceCards(form);
                if (onChange) onChange(radio.value);
            });
        });
    }

    function initShapeUi(form) {
        var shapeConfig = {};
        try { shapeConfig = JSON.parse(form.dataset.shapeUi || '{}'); } catch (e) { shapeConfig = {}; }
        var hint = document.getElementById('fbMeasureHint');
        var preview = document.getElementById('fbMeasurePreview');
        var labelA = document.getElementById('fbLabelA');
        var labelB = document.getElementById('fbLabelB');
        var labelC = document.getElementById('fbLabelC');
        var inputLabelA = document.getElementById('fbInputLabelA');
        var inputLabelB = document.getElementById('fbInputLabelB');
        var inputLabelC = document.getElementById('fbInputLabelC');
        var inputLabelD = document.getElementById('fbInputLabelD');
        var heightWrap = document.getElementById('fbHeightWrap');
        var heightInput = document.getElementById('fbHeight');
        var descMap = {
            straight: 'Klassische lineare Abdeckung für Achsen und Führungen.',
            u: 'Für Führungen mit seitlicher Umschließung.',
            l: 'Wenn zwei Seiten geschützt werden müssen.',
            c: 'Seitlich offene Form für spezielle Einbauräume.',
            g: 'Versetzte Geometrie mit Rücksprung oder Eingriff.',
            box: 'Mehrseitiger Schutz für komplexere Anwendungen.',
            pult: 'Schräge Form für Pult- und Bedienbereiche.',
            roof: 'Dachförmige Abdeckung für obere Bereiche.',
            kastenbalg: 'Räumlicher Balg für größere Volumen.',
            special: 'Freiform oder Sondergeometrie, bitte Skizze ergänzen.'
        };
        form.querySelectorAll('[data-shape-description]').forEach(function (el) {
            var key = el.getAttribute('data-shape-description');
            el.textContent = descMap[key] || '';
        });

        return function apply(shape) {
            var cfg = shapeConfig[shape] || shapeConfig.straight || { labels: ['Breite (A)', 'Tiefe (B)', 'Länge (C)'], show_height: false };
            var labels = cfg.labels || ['Breite (A)', 'Tiefe (B)', 'Länge (C)'];
            if (hint) hint.textContent = cfg.hint || '';
            if (preview) preview.src = '/nolte_faltenbalg_configurator/static/src/img/' + shape + '.svg';
            if (labelA) labelA.textContent = labels[0] || 'Maß A';
            if (labelB) labelB.textContent = labels[1] || 'Maß B';
            if (labelC) labelC.textContent = labels[2] || 'Maß C';
            if (inputLabelA) inputLabelA.textContent = labels[0] || 'Maß A';
            if (inputLabelB) inputLabelB.textContent = labels[1] || 'Maß B';
            if (inputLabelC) inputLabelC.textContent = labels[2] || 'Maß C';
            if (cfg.show_height) {
                if (heightWrap) heightWrap.classList.remove('d-none');
                if (heightInput) heightInput.disabled = false;
                if (inputLabelD) inputLabelD.textContent = cfg.height_label || 'Höhe (D)';
            } else {
                if (heightWrap) heightWrap.classList.add('d-none');
                if (heightInput) { heightInput.disabled = true; heightInput.value = ''; }
            }
        };
    }

    function initWizard(form) {
        if (form.dataset.fbWizardInit === '1') return;
        form.dataset.fbWizardInit = '1';
        var steps = Array.prototype.slice.call(form.querySelectorAll('.fb-step'));
        var pills = Array.prototype.slice.call(form.querySelectorAll('.fb-step-pill'));
        var progressBar = document.getElementById('fbProgressBar');
        var prevBtn = document.getElementById('fbPrevBtn');
        var nextBtn = document.getElementById('fbNextBtn');
        var submitBtn = document.getElementById('fbSubmitBtn');
        var current = 0;
        var applyShapeUi = initShapeUi(form);

        function render() {
            steps.forEach(function (step, index) { step.classList.toggle('is-active', index === current); });
            pills.forEach(function (pill, index) {
                pill.classList.toggle('is-active', index === current);
                pill.setAttribute('aria-current', index === current ? 'step' : 'false');
            });
            if (progressBar) progressBar.style.width = (((current + 1) / steps.length) * 100) + '%';
            if (prevBtn) prevBtn.disabled = current === 0;
            if (nextBtn) nextBtn.classList.toggle('d-none', current === steps.length - 1);
            if (submitBtn) submitBtn.classList.toggle('d-none', current !== steps.length - 1);
            updateChoiceCards(form);
        }

        if (prevBtn) prevBtn.addEventListener('click', function () { if (current > 0) { current -= 1; render(); } });
        if (nextBtn) nextBtn.addEventListener('click', function () { if (!isStepValid(steps[current])) return; if (current < steps.length - 1) { current += 1; render(); } });
        pills.forEach(function (pill, index) {
            pill.addEventListener('click', function () { if (index <= current || isStepValid(steps[current])) { current = index; render(); } });
        });

        bindChoiceCards(form, applyShapeUi);
        var selected = form.querySelector('input[name="shape"]:checked');
        applyShapeUi(selected ? selected.value : 'straight');
        render();
    }

    function boot() { var form = document.getElementById('fbWizardForm'); if (form) initWizard(form); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
