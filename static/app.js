// Global State
let selectedFiles = [];
let selectedUrls = [];
let sampleFiles = [];
let processedProfiles = [];
let explainabilityReport = {};
let formattedOutput = [];
let provenanceRecords = [];

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const uploadedFilesList = document.getElementById('uploaded-files-list');
const samplesContainer = document.getElementById('samples-container');
const runBtn = document.getElementById('run-btn');
const candidatesGrid = document.getElementById('candidates-grid');
const candidatesCountBadge = document.getElementById('candidates-count');
const terminalLogs = document.getElementById('terminal-logs');
const jsonOutputCode = document.getElementById('json-output');
const jsonReportCode = document.getElementById('json-report');
const outputCandidateSelector = document.getElementById('output-candidate-selector');
const outputConfigEditor = document.getElementById('output-config-editor');

// Metrics
const metricSources = document.getElementById('metric-sources');
const metricProfiles = document.getElementById('metric-profiles');
const metricDedupRate = document.getElementById('metric-dedup-rate');

// Step Elements
const steps = {
    ingest: document.getElementById('step-ingest'),
    normalize: document.getElementById('step-normalize'),
    resolve: document.getElementById('step-resolve'),
    merge: document.getElementById('step-merge'),
    confidence: document.getElementById('step-confidence'),
    output: document.getElementById('step-output')
};

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    fetchSamples();
    fetchOutputConfig();
    setupDragAndDrop();
    setupTabListeners();
    setupDrawerTabListeners();
    setupRunListener();
    setupUrlIngestion();
    setupOutputSelectorListener();
});

function setupUrlIngestion() {
    const addUrlBtn = document.getElementById('add-url-btn');
    const urlInput = document.getElementById('url-input');

    if (addUrlBtn && urlInput) {
        addUrlBtn.addEventListener('click', addUrl);
        urlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') addUrl();
        });
    }
}

function addUrl() {
    const urlInput = document.getElementById('url-input');
    const url = urlInput.value.trim();
    if (url) {
        if (!selectedUrls.includes(url)) {
            selectedUrls.push(url);
            renderUploadedFilesAndUrls();
            updateButtonState();
        }
        urlInput.value = '';
    }
}

// Fetch Sample Files
async function fetchSamples() {
    try {
        const res = await fetch('/api/samples');
        sampleFiles = await res.json();
        renderSamples();
    } catch (e) {
        samplesContainer.innerHTML = '<div class="error-msg">Failed to load samples</div>';
    }
}

// Fetch Output Configuration
async function fetchOutputConfig() {
    try {
        const res = await fetch('/api/config');
        const config = await res.json();
        if (outputConfigEditor) {
            outputConfigEditor.value = JSON.stringify(config, null, 2);
        }
    } catch (e) {
        console.error("Failed to load output config", e);
    }
}

// Setup listener for candidate output selector dropdown
function setupOutputSelectorListener() {
    if (outputCandidateSelector) {
        outputCandidateSelector.addEventListener('change', () => {
            const selectedVal = outputCandidateSelector.value;
            if (selectedVal === 'all') {
                jsonOutputCode.textContent = JSON.stringify(formattedOutput, null, 2);
            } else {
                const idx = parseInt(selectedVal, 10);
                if (!isNaN(idx) && formattedOutput[idx]) {
                    jsonOutputCode.textContent = JSON.stringify(formattedOutput[idx], null, 2);
                } else {
                    jsonOutputCode.textContent = '{}';
                }
            }
        });
    }
}

// Repopulate output dropdown selector with current candidate names
function populateOutputSelector() {
    if (!outputCandidateSelector) return;
    outputCandidateSelector.innerHTML = '<option value="all">All Candidates (Combined Array)</option>';
    formattedOutput.forEach((profile, idx) => {
        const name = profile.name || profile.full_name || `Candidate ${idx + 1}`;
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = name;
        outputCandidateSelector.appendChild(opt);
    });
}

// Render Samples
function renderSamples() {
    if (!sampleFiles.length) {
        samplesContainer.innerHTML = '<div class="text-muted">No sample files found</div>';
        return;
    }

    samplesContainer.innerHTML = sampleFiles.map(file => `
        <label class="sample-checkbox-item">
            <input type="checkbox" value="${file.name}" onchange="updateButtonState()">
            <div class="sample-meta">
                <span class="sample-name">${file.name}</span>
                <span class="sample-size">${formatBytes(file.size)} • ${file.type.toUpperCase()}</span>
            </div>
        </label>
    `).join('');
}

// Helper: Format bytes
function formatBytes(bytes, decimals = 1) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

// Setup Drag & Drop Handlers
function setupDragAndDrop() {
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }, false);

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });
}

// Handle selected/dropped files
function handleFiles(files) {
    for (let file of files) {
        // Prevent duplicate loads
        if (!selectedFiles.some(f => f.name === file.name)) {
            selectedFiles.push(file);
        }
    }
    renderUploadedFilesAndUrls();
    updateButtonState();
}

// Render local files and URLs queue
function renderUploadedFilesAndUrls() {
    const filesHtml = selectedFiles.map((file, idx) => `
        <div class="file-item">
            <span title="${file.name}">📄 ${file.name}</span>
            <button onclick="removeFile(${idx})">&times;</button>
        </div>
    `).join('');

    const urlsHtml = selectedUrls.map((url, idx) => `
        <div class="file-item">
            <span title="${url}" style="color: var(--accent-purple); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 80%;">🔗 ${url}</span>
            <button onclick="removeUrl(${idx})">&times;</button>
        </div>
    `).join('');

    uploadedFilesList.innerHTML = filesHtml + urlsHtml;
}

window.removeFile = function(index) {
    selectedFiles.splice(index, 1);
    renderUploadedFilesAndUrls();
    updateButtonState();
};

window.removeUrl = function(index) {
    selectedUrls.splice(index, 1);
    renderUploadedFilesAndUrls();
    updateButtonState();
};

// Update "Run Ingestion Pipeline" button status
function updateButtonState() {
    const hasUploads = selectedFiles.length > 0 || selectedUrls.length > 0;
    const checkedSamples = getSelectedSamples();
    const hasSamples = checkedSamples.length > 0;

    runBtn.disabled = !(hasUploads || hasSamples);
}

// Retrieve selected sample keys
function getSelectedSamples() {
    const checkboxes = samplesContainer.querySelectorAll('input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// Setup running pipeline
function setupRunListener() {
    runBtn.addEventListener('click', async () => {
        // Change UI state to loading
        runBtn.disabled = true;
        runBtn.innerHTML = `
            <span>Running Pipeline...</span>
            <div class="spinner-small"></div>
        `;
        resetPipelineFlow();
        
        // Assemble form payload
        const formData = new FormData();
        selectedFiles.forEach(file => {
            formData.append('files', file);
        });
        
        if (selectedUrls.length) {
            formData.append('urls', JSON.stringify(selectedUrls));
        }
        
        const samples = getSelectedSamples();
        if (samples.length) {
            formData.append('samples', JSON.stringify(samples));
        }

        if (outputConfigEditor && outputConfigEditor.value.trim()) {
            formData.append('output_config', outputConfigEditor.value.trim());
        }

        // Start flow step animations
        const pipelineAnim = startPipelineFlowAnimation();

        try {
            const res = await fetch('/api/process', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            clearInterval(pipelineAnim);

            if (data.success) {
                // Store results
                processedProfiles = data.profiles || [];
                explainabilityReport = data.report || {};
                formattedOutput = data.output || [];
                provenanceRecords = data.provenance || [];
                
                // Show logs
                terminalLogs.textContent = data.logs || 'No logs captured.';
                populateOutputSelector();
                jsonOutputCode.textContent = JSON.stringify(formattedOutput, null, 2);
                jsonReportCode.textContent = JSON.stringify(explainabilityReport, null, 2);
                
                // Mark all steps as complete
                completeAllPipelineSteps();

                // Render profiles
                renderProfiles();
                updateMetrics(samples.length + selectedFiles.length + selectedUrls.length, processedProfiles.length);
            } else {
                failPipelineFlow();
                terminalLogs.textContent = `Pipeline Error:\n${data.error}\n\nLogs:\n${data.logs}`;
                alert(`Error processing pipeline: ${data.error}`);
            }
        } catch (err) {
            clearInterval(pipelineAnim);
            failPipelineFlow();
            terminalLogs.textContent = `Execution failed:\n${err.message}`;
            alert(`Execution failed: ${err.message}`);
        } finally {
            updateButtonState();
            runBtn.innerHTML = `
                <span>Run Ingestion Pipeline</span>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M5 12H19M19 12L12 5M19 12L12 19" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            `;
        }
    });
}

// Reset steps visual styles
function resetPipelineFlow() {
    Object.values(steps).forEach(step => {
        step.className = 'flow-step';
    });
}

// Animate flow timeline steps
function startPipelineFlowAnimation() {
    const keys = Object.keys(steps);
    let activeIndex = 0;
    
    // Set first processing
    steps[keys[0]].className = 'flow-step processing';

    return setInterval(() => {
        if (activeIndex < keys.length - 1) {
            steps[keys[activeIndex]].className = 'flow-step completed';
            activeIndex++;
            steps[keys[activeIndex]].className = 'flow-step processing';
        }
    }, 700);
}

function completeAllPipelineSteps() {
    Object.values(steps).forEach(step => {
        step.className = 'flow-step completed';
    });
}

function failPipelineFlow() {
    Object.values(steps).forEach(step => {
        if (step.classList.contains('processing')) {
            step.className = 'flow-step';
        }
    });
}

// Update Top Dashboard Metrics
function updateMetrics(sourceCount, profileCount) {
    metricSources.textContent = sourceCount;
    metricProfiles.textContent = profileCount;
    
    if (sourceCount > 0) {
        const rate = ((sourceCount - profileCount) / sourceCount) * 100;
        metricDedupRate.textContent = `${rate.toFixed(0)}%`;
    } else {
        metricDedupRate.textContent = '0%';
    }
}

// Render Candidate Cards list
function renderProfiles() {
    if (!processedProfiles.length) {
        candidatesGrid.innerHTML = `
            <div class="placeholder-card">
                <p>No profiles generated. Verify that your input file contains valid profiles.</p>
            </div>
        `;
        candidatesCountBadge.textContent = '0 profiles';
        return;
    }

    candidatesCountBadge.textContent = `${processedProfiles.length} profiles`;
    candidatesGrid.innerHTML = processedProfiles.map(p => {
        const score = p.overall_confidence || 0.0;
        let scoreClass = 'score-low';
        if (score >= 0.85) scoreClass = 'score-high';
        else if (score >= 0.6) scoreClass = 'score-medium';
        
        return `
            <div class="candidate-card" onclick="inspectProfile('${p.candidate_id}')">
                <div class="candidate-info">
                    <h4>${p.full_name || 'Unknown'}</h4>
                    <p class="headline">${p.headline || 'No Headline Provided'}</p>
                    <div class="candidate-meta-row">
                        <span>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                            ${p.merged_from ? p.merged_from.length : 1} Sources
                        </span>
                        <span>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                            ${p.skills ? p.skills.length : 0} Skills
                        </span>
                    </div>
                </div>
                <div class="card-score">
                    <span class="score-badge ${scoreClass}">${(score * 100).toFixed(0)}%</span>
                    <span class="lbl">Confidence</span>
                </div>
            </div>
        `;
    }).join('');
}

// Tab Swapping
function setupTabListeners() {
    const tabBtns = document.querySelectorAll('.tabs .tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelector('.tabs .tab-btn.active').classList.remove('active');
            document.querySelector('.tab-content.active').classList.remove('active');
            
            btn.classList.add('active');
            const targetId = btn.getAttribute('data-tab');
            document.getElementById(targetId).classList.add('active');
        });
    });
}

function setupDrawerTabListeners() {
    const tabBtns = document.querySelectorAll('.drawer-tabs .drawer-tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelector('.drawer-tabs .drawer-tab-btn.active').classList.remove('active');
            document.querySelector('.drawer-tab-content.active').classList.remove('active');
            
            btn.classList.add('active');
            const targetId = btn.getAttribute('data-drawer-tab');
            document.getElementById(targetId).classList.add('active');
        });
    });
}

// Copy Code Helper
window.copyText = function(elementId) {
    const content = document.getElementById(elementId).textContent;
    navigator.clipboard.writeText(content).then(() => {
        alert('Copied to clipboard!');
    }).catch(err => {
        alert('Failed to copy text: ' + err);
    });
};

// Inspect specific candidate profile details inside Drawer
window.inspectProfile = function(candidateId) {
    const profile = processedProfiles.find(p => p.candidate_id === candidateId);
    if (!profile) return;

    // Set drawer basic info
    document.getElementById('drawer-name').textContent = profile.full_name || 'Unknown Candidate';
    document.getElementById('drawer-headline').textContent = profile.headline || 'No headline assertion';
    document.getElementById('drawer-yoe').textContent = profile.years_experience !== null ? `${profile.years_experience} YOE` : 'YOE Unknown';
    document.getElementById('drawer-sources-badge').textContent = `${profile.merged_from ? profile.merged_from.length : 1} Sources`;
    
    // Set score circle ring
    const score = profile.overall_confidence || 0.0;
    const strokeDash = 213.6; // Circumference of circle with r=34
    const offset = strokeDash - (strokeDash * score);
    const progressPath = document.getElementById('drawer-gauge-path');
    
    // Color circle by confidence
    let ringColor = '#ef4444';
    if (score >= 0.85) ringColor = '#10b981';
    else if (score >= 0.6) ringColor = '#f59e0b';
    progressPath.style.stroke = ringColor;
    
    progressPath.style.strokeDashoffset = offset;
    document.getElementById('drawer-gauge-val').textContent = `${(score * 100).toFixed(0)}%`;
    document.getElementById('drawer-gauge-val').style.color = ringColor;

    // Emails
    const emailsEl = document.getElementById('drawer-emails');
    if (profile.emails && profile.emails.length) {
        emailsEl.innerHTML = profile.emails.map(e => `<div>${e}</div>`).join('');
    } else {
        emailsEl.innerHTML = '<span class="text-muted">-</span>';
    }

    // Phones
    const phonesEl = document.getElementById('drawer-phones');
    if (profile.phones && profile.phones.length) {
        phonesEl.innerHTML = profile.phones.map(p => `<div>${p}</div>`).join('');
    } else {
        phonesEl.innerHTML = '<span class="text-muted">-</span>';
    }

    // Location
    const locEl = document.getElementById('drawer-location');
    if (profile.location && (profile.location.city || profile.location.country)) {
        const parts = [profile.location.city, profile.location.region, profile.location.country].filter(Boolean);
        locEl.textContent = parts.join(', ');
    } else {
        locEl.innerHTML = '<span class="text-muted">-</span>';
    }

    // Links List
    const linksEl = document.getElementById('drawer-links');
    let linksHtml = '';
    if (profile.links) {
        if (profile.links.linkedin) {
            linksHtml += `<a href="${profile.links.linkedin}" target="_blank" class="link-anchor">LinkedIn</a>`;
        }
        if (profile.links.github) {
            linksHtml += `<a href="${profile.links.github}" target="_blank" class="link-anchor">GitHub</a>`;
        }
        if (profile.links.portfolio) {
            linksHtml += `<a href="${profile.links.portfolio}" target="_blank" class="link-anchor">Portfolio</a>`;
        }
        if (profile.links.other && profile.links.other.length) {
            profile.links.other.forEach(url => {
                const label = new URL(url).hostname.replace('www.', '');
                linksHtml += `<a href="${url}" target="_blank" class="link-anchor">${label}</a>`;
            });
        }
    }
    linksEl.innerHTML = linksHtml || '<span class="text-muted">No links available</span>';

    // Skills Taxonomy Map
    const skillsEl = document.getElementById('drawer-skills');
    if (profile.skills && profile.skills.length) {
        skillsEl.innerHTML = profile.skills.map(s => `
            <span class="skill-tag" title="Sources: ${s.sources.join(', ')} (Confidence: ${(s.confidence*100).toFixed(0)}%)">
                ${s.name}
            </span>
        `).join('');
    } else {
        skillsEl.innerHTML = '<span class="text-muted">No skills mapped</span>';
    }

    // Timeline Experience Items
    const timelineEl = document.getElementById('drawer-timeline');
    if (profile.experience && profile.experience.length) {
        timelineEl.innerHTML = profile.experience.map(exp => `
            <div class="timeline-item">
                <div class="timeline-meta">
                    <h5>${exp.title || 'Role'}</h5>
                    <span class="date">${exp.start_date || 'Start'} — ${exp.end_date || 'Present'}</span>
                </div>
                <div class="timeline-company">${exp.company || 'Company'}</div>
                <p class="timeline-desc">${exp.description || ''}</p>
            </div>
        `).join('');
    } else {
        timelineEl.innerHTML = '<span class="text-muted">No work history entries</span>';
    }

    // Education Items
    const eduEl = document.getElementById('drawer-education');
    if (profile.education && profile.education.length) {
        eduEl.innerHTML = profile.education.map(edu => `
            <div class="edu-item">
                <h5>${edu.degree || 'Degree'}</h5>
                <div class="edu-institution">${edu.institution || 'Institution'}</div>
                <div class="edu-meta">
                    <span>${edu.field_of_study || ''}</span>
                    <span>${edu.start_date || ''} — ${edu.end_date || ''}</span>
                </div>
            </div>
        `).join('');
    } else {
        eduEl.innerHTML = '<span class="text-muted">No education entries</span>';
    }

    // Provenance Audit logs
    const auditRowsEl = document.getElementById('drawer-audit-rows');
    const cProvenance = provenanceRecords.filter(r => r.candidate_id === candidateId);
    
    if (cProvenance.length) {
        auditRowsEl.innerHTML = cProvenance.map(r => {
            const shortPath = r.source_path ? r.source_path.substring(r.source_path.lastIndexOf('/') + 1) : '-';
            const cleanVal = typeof r.value === 'object' ? JSON.stringify(r.value) : r.value;
            
            return `
                <tr>
                    <td class="field-cell">${r.field}</td>
                    <td class="val-cell">${cleanVal !== null ? cleanVal : '<span class="text-muted">null</span>'}</td>
                    <td><span class="badge">${r.method || 'direct'}</span></td>
                    <td title="${r.source_path}">${shortPath}</td>
                    <td class="conf-cell">${(r.confidence * 100).toFixed(0)}%</td>
                </tr>
            `;
        }).join('');
    } else {
        auditRowsEl.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center;" class="text-muted">No provenance records logged for this candidate</td>
            </tr>
        `;
    }

    // Set first tab active in drawer
    document.querySelector('.drawer-tabs .drawer-tab-btn.active').classList.remove('active');
    document.querySelector('.drawer-tab-content.active').classList.remove('active');
    document.querySelector('.drawer-tabs .drawer-tab-btn').classList.add('active');
    document.getElementById('dtab-overview').classList.add('active');

    // Open Drawer Drawer
    document.getElementById('profile-drawer').classList.add('open');
};

window.closeDrawer = function() {
    document.getElementById('profile-drawer').classList.remove('open');
};
