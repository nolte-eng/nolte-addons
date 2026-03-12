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
        var lmaxInput = document.getElementById('fbLmax');
        var extraFields = {
            d: {wrap: document.getElementById('fbHeightWrap'), input: document.getElementById('fbHeight'), label: document.getElementById('fbInputLabelD')},
            e: {wrap: document.getElementById('fbExtraEWrap'), input: document.getElementById('fbExtraE'), label: document.getElementById('fbInputLabelE')},
            f: {wrap: document.getElementById('fbExtraFWrap'), input: document.getElementById('fbExtraF'), label: document.getElementById('fbInputLabelF')},
            g: {wrap: document.getElementById('fbExtraGWrap'), input: document.getElementById('fbExtraG'), label: document.getElementById('fbInputLabelG')}
        };
        var descMap = {
            straight: 'Klassische lineare Abdeckung für Achsen und Führungen.',
            u: 'Für Führungen mit seitlicher Umschließung.',
            l: 'Wenn zwei Seiten geschützt werden müssen.',
            c: 'Seitlich offene Form für spezielle Einbauräume.',
            g: 'Versetzte Geometrie mit Rücksprung oder Eingriff.',
            box: 'Mehrseitiger Schutz für komplexere Anwendungen.',
            pult: 'Schräge Form für Pult- und Bedienbereiche.',
            roof: 'Dachförmige Abdeckung für obere Bereiche.',
            kastenbalg: 'Kastenform für mehrseitige Abdeckungen.',
            special: 'Freiform oder Sondergeometrie, bitte Skizze ergänzen.'
        };
        form.querySelectorAll('[data-shape-description]').forEach(function (el) {
            var key = el.getAttribute('data-shape-description');
            el.textContent = descMap[key] || '';
        });

        return function apply(shape) {
            var cfg = shapeConfig[shape] || shapeConfig.straight || { labels: ['Breite (A)', 'Tiefe (B)', 'Gesamtlänge'], show_height: false };
            var labels = cfg.labels || ['Breite (A)', 'Tiefe (B)', 'Gesamtlänge'];
            if (hint) hint.textContent = cfg.hint || '';
            var previewShape = shape === 'kastenbalg' ? 'box' : shape;
            if (preview) preview.src = '/nolte_faltenbalg_configurator/static/src/img/' + previewShape + '.svg';
            if (labelA) labelA.textContent = labels[0] || 'Maß A';
            if (labelB) labelB.textContent = labels[1] || 'Maß B';
            if (labelC) labelC.textContent = labels[2] || 'Maß C';
            if (inputLabelA) inputLabelA.textContent = labels[0] || 'Maß A';
            if (inputLabelB) inputLabelB.textContent = labels[1] || 'Maß B';
            if (inputLabelC) inputLabelC.textContent = labels[2] || 'Maß C';
            if (lmaxInput) lmaxInput.value = (document.getElementById('fbLength') || {}).value || '';
            Object.keys(extraFields).forEach(function (key) {
                var field = extraFields[key];
                if (!field || !field.wrap || !field.input) return;
                field.wrap.classList.add('d-none');
                field.input.disabled = true;
                field.input.required = false;
                field.input.value = '';
                if (field.label) field.label.textContent = 'Maß ' + key.toUpperCase();
            });
            (cfg.extra_fields || []).forEach(function (fieldCfg) {
                var field = extraFields[fieldCfg.key];
                if (!field || !field.wrap || !field.input) return;
                field.wrap.classList.remove('d-none');
                field.input.disabled = false;
                field.input.required = true;
                if (field.label) field.label.textContent = fieldCfg.label || ('Maß ' + fieldCfg.key.toUpperCase());
            });
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
        var lenInput = document.getElementById('fbLength');
        var lminInput = document.getElementById('fbLmin');
        var hubInput = document.getElementById('fbHub');
        var lmaxInput = document.getElementById('fbLmax');
        var foldPitchInput = document.getElementById('fbFoldPitch');
        var foldCountInput = document.getElementById('fbFoldCount');
        var hubValidation = document.getElementById('fbHubValidation');
        function formatNumber(value, decimals) {
            if (value === '' || value === null || typeof value === 'undefined' || isNaN(value)) return '';
            var fixed = Number(value).toFixed(decimals || 2);
            return fixed.replace(/\.00$/, '').replace(/(\.\d*[1-9])0+$/, '$1');
        }
        function updateFoldCount(hub) {
            var pitch = parseFloat(foldPitchInput && foldPitchInput.value || 0);
            if (foldCountInput) {
                if (hub > 0 && pitch > 0) foldCountInput.value = String(Math.max(Math.round(hub / pitch), 1));
                else foldCountInput.value = '';
            }
        }
        function updateHubValidation(lmax, lmin, hub) {
            var message = '';
            if (lmax > 0) {
                if (lmin > lmax) message = 'Lmin darf nicht größer als Lmax sein.';
                else if (hub > lmax) message = 'Der Hub darf nicht größer als Lmax sein.';
                else if (lmin > 0 && hub > 0) {
                    var diff = Math.abs((lmax - lmin) - hub);
                    if (diff > 0.51) message = 'Hub muss der Differenz aus Lmax und Lmin entsprechen.';
                }
            }
            [lminInput, hubInput].forEach(function (field) { if (field) field.setCustomValidity(message); });
            if (hubValidation) {
                hubValidation.textContent = message;
                hubValidation.classList.toggle('d-none', !message);
            }
        }
        function syncHubFields(source) {
            var lmax = parseFloat(lenInput && lenInput.value || 0);
            var lmin = parseFloat(lminInput && lminInput.value || 0);
            var hub = parseFloat(hubInput && hubInput.value || 0);
            if (lmaxInput) lmaxInput.value = lenInput && lenInput.value ? lenInput.value : '';
            if (source === 'lmin' && lmax && !isNaN(lmin)) {
                hub = Math.max(lmax - lmin, 0);
                if (hubInput) hubInput.value = formatNumber(hub);
            } else if (source === 'hub' && lmax && !isNaN(hub)) {
                lmin = Math.max(lmax - hub, 0);
                if (lminInput) lminInput.value = formatNumber(lmin);
            }
            updateHubValidation(lmax, lmin, hub);
            updateFoldCount(hub);
        }
        if (lenInput) lenInput.addEventListener('input', function () { syncHubFields(); });
        if (lminInput) lminInput.addEventListener('input', function () { syncHubFields('lmin'); });
        if (hubInput) hubInput.addEventListener('input', function () { syncHubFields('hub'); });
        if (foldPitchInput) foldPitchInput.addEventListener('input', function () { syncHubFields(); });
        var selected = form.querySelector('input[name="shape"]:checked');
        applyShapeUi(selected ? selected.value : 'straight');
        syncHubFields();
        render();
    }

    function boot() { var form = document.getElementById('fbWizardForm'); if (form) initWizard(form); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
