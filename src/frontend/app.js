document.addEventListener('DOMContentLoaded', async () => {
    // State
    let mode = 'pdf'; // 'pdf' or 'text'
    let currentBook = null;
    let sentences = [];
    let currentIndex = -1;
    let isPlaying = false;
    let isPreparing = false;
    let isContinuous = true;
    
    let currentPage = 0;
    let totalPages = 0;
    let currentNativeSpeed = 1.0;
    
    // Background Prefetching State
    let prefetchedPage = null;
    let isFetchingNextPage = false;
    
    // Audio Queue
    let audioCache = {}; // index -> url
    let isSynthesizing = {}; // index -> boolean
    
    // Constants
    const REQUIRED_BUFFER_AHEAD = 7; // Increased for background queue buffer
    const PREFETCH_LIMIT = 30; // How many sentences to keep queued ahead
    
    // DOM Elements
    const audioPlayer = document.getElementById('audio-player');
    const playPauseBtn = document.getElementById('play-pause-btn');
    const stopBtn = document.getElementById('stop-btn');
    const playIcon = playPauseBtn.querySelector('i');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const bufferStatus = document.getElementById('buffer-status');
    const textContainer = document.getElementById('text-container');
    const pdfContainer = document.getElementById('pdf-container');
    const pdfFrame = document.getElementById('pdf-frame');
    const contToggle = document.getElementById('continuous-toggle');
    const speedSlider = document.getElementById('speed-slider');
    const speedVal = document.getElementById('speed-val');
    const volSlider = document.getElementById('volume-slider');
    
    // UI Layout Toggles
    const btnModePdf = document.getElementById('btn-mode-pdf');
    const btnModeText = document.getElementById('btn-mode-text');
    const pdfControls = document.getElementById('pdf-controls');
    const customTextInput = document.getElementById('custom-text-input');
    const readerView = document.getElementById('reader-view');
    const pageControls = document.getElementById('page-controls');
    const togglePdfViewBtn = document.getElementById('toggle-pdf-view');
    const sidebar = document.getElementById('sidebar');
    const toggleSidebarBtn = document.getElementById('toggle-sidebar');
    const expandSidebarBtn = document.getElementById('expand-sidebar');
    
    const modelToggleContainer = document.getElementById('model-toggle-container');

    // Sidebar Toggle
    toggleSidebarBtn.addEventListener('click', () => {
        sidebar.classList.add('collapsed');
        expandSidebarBtn.classList.remove('hidden');
    });
    expandSidebarBtn.addEventListener('click', () => {
        sidebar.classList.remove('collapsed');
        expandSidebarBtn.classList.add('hidden');
    });

    // PDF View Toggle
    let showPdf = false;
    togglePdfViewBtn.addEventListener('click', () => {
        showPdf = !showPdf;
        if (showPdf) {
            textContainer.classList.add('hidden');
            pdfContainer.classList.remove('hidden');
            togglePdfViewBtn.innerHTML = '<i class="fa-solid fa-align-left"></i> Show Text';
            // Ensure the iframe is on the correct page when shown
            if (currentBook) {
                const encodedBook = encodeURIComponent(currentBook).replace(/\(/g, '%28').replace(/\)/g, '%29');
                pdfFrame.src = `/pdf-file/${encodedBook}#page=${currentPage + 1}`;
            }
        } else {
            pdfContainer.classList.add('hidden');
            textContainer.classList.remove('hidden');
            togglePdfViewBtn.innerHTML = '<i class="fa-solid fa-file-pdf"></i> Show PDF';
            // re-scroll
            const activeSpan = document.getElementById(`s-${currentIndex}`);
            if (activeSpan) activeSpan.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    });

    // Initialize Library
    async function initLibrary() {
        try {
            const res = await fetch('/api/library');
            const data = await res.json();
            const list = document.getElementById('library-list');
            list.innerHTML = '';
            
            if (data.books.length === 0) {
                list.innerHTML = '<div style="color: #94a3b8; font-size: 0.85rem; padding: 10px;">No books uploaded yet.</div>';
                return;
            }
            
            data.books.forEach(book => {
                const item = document.createElement('div');
                item.className = `book-item ${currentBook === book.id ? 'active' : ''}`;
                item.innerText = book.id;
                item.title = `Saved at Page ${book.page + 1}`;
                item.addEventListener('click', () => loadBookFromLibrary(book.id));
                list.appendChild(item);
            });
        } catch (e) {
            console.error("Failed to load library", e);
        }
    }

    async function loadBookFromLibrary(book_id) {
        currentBook = book_id;
        bufferStatus.innerText = "Loading...";
        
        // Update active class
        initLibrary();
        
        // Setup toggle button, but don't set iframe src yet because it's hidden.
        // Setting PDF src while display:none causes "Failed to get StreamContainer" in Chrome.
        togglePdfViewBtn.classList.remove('hidden');
        
        try {
            // Need total pages? We can just fetch the first page to get metadata, 
            // but the API currently doesn't return totalPages on /page/ load. 
            // We'll trust the user state.
            const stateRes = await fetch(`/api/load_state/${currentBook}`);
            const state = await stateRes.json();
            await loadPage(state.page || 0, state.sentence_idx || 0);
        } catch(e) {
            console.error("Failed to load book state", e);
        }
    }

    btnModePdf.addEventListener('click', () => {
        mode = 'pdf';
        btnModePdf.classList.add('active');
        btnModeText.classList.remove('active');
        pdfControls.classList.remove('hidden');
        customTextInput.classList.add('hidden');
        readerView.classList.remove('hidden');
        togglePdfViewBtn.classList.remove('hidden');
    });

    btnModeText.addEventListener('click', () => {
        mode = 'text';
        btnModeText.classList.add('active');
        btnModePdf.classList.remove('active');
        pdfControls.classList.add('hidden');
        customTextInput.classList.remove('hidden');
        readerView.classList.add('hidden');
        togglePdfViewBtn.classList.add('hidden');
        pauseAudio();
    });

    // Settings
    contToggle.addEventListener('change', (e) => isContinuous = e.target.checked);
    speedSlider.addEventListener('input', (e) => {
        const uiSpeed = parseFloat(e.target.value);
        audioPlayer.playbackRate = uiSpeed / currentNativeSpeed; 
        speedVal.innerText = `${uiSpeed.toFixed(1)}x`;
    });
    
    modelToggleContainer.addEventListener('change', async (e) => {
        if (e.target.name === 'tts-model') {
            const val = e.target.value;
            try {
                bufferStatus.innerText = `Loading ${val}...`;
                const res = await fetch('/api/set_model', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_name: val })
                });
                const data = await res.json();
                currentNativeSpeed = data.native_speed || 1.0;
                bufferStatus.innerText = `Model set to ${val}`;
                
                // Clear audio cache so we don't play old model's audio
                await fetch('/api/clear_queue', { method: 'POST' });
                audioCache = {};
                isSynthesizing = {};
                
                // Update active playback rate
                const uiSpeed = parseFloat(speedSlider.value);
                audioPlayer.playbackRate = uiSpeed / currentNativeSpeed;
                
            } catch(err) { console.error(err); }
        }
    });

    volSlider.addEventListener('input', (e) => {
        audioPlayer.volume = e.target.value;
    });

    // Save state
    async function saveState() {
        if (!currentBook || mode !== 'pdf' || currentIndex < 0 || !sentences[currentIndex]) return;
        const currentSentence = sentences[currentIndex];
        try {
            await fetch('/api/save_state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    book_id: currentBook, 
                    page_num: currentSentence.page, 
                    sentence_idx: currentSentence.rel_idx 
                })
            });
        } catch (e) { console.error("Failed to save state", e); }
    }

    // PDF Upload
    document.getElementById('pdf-upload').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        bufferStatus.innerText = "Uploading...";
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const res = await fetch('/api/upload', { method: 'POST', body: formData });
            const data = await res.json();
            currentBook = data.book_id;
            totalPages = data.num_pages;
            
            // Setup toggle button
            togglePdfViewBtn.classList.remove('hidden');
            
            initLibrary(); // Refresh library list
            
            const stateRes = await fetch(`/api/load_state/${currentBook}`);
            const state = await stateRes.json();
            await loadPage(state.page || 0, state.sentence_idx || 0);
        } catch (err) {
            console.error(err);
            bufferStatus.innerText = "Upload failed";
        }
    });

    // Custom Text
    document.getElementById('process-text-btn').addEventListener('click', async () => {
        const text = document.getElementById('raw-text').value;
        if (!text.trim()) return;
        
        bufferStatus.innerText = "Processing...";
        try {
            const res = await fetch('/api/custom_text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            const data = await res.json();
            sentences = data.sentences; 
            
            btnModeText.classList.remove('active');
            btnModePdf.classList.remove('active');
            customTextInput.classList.add('hidden');
            readerView.classList.remove('hidden');
            pageControls.classList.add('hidden');
            togglePdfViewBtn.classList.add('hidden');
            document.getElementById('current-title').innerText = "Custom Text";
            
            renderSentences();
            setIndex(0);
        } catch (err) {
            console.error(err);
            bufferStatus.innerText = "Processing failed";
        }
    });

    // Pagination
    document.getElementById('prev-page').addEventListener('click', () => {
        if (currentPage > 0) loadPage(currentPage - 1, 0);
    });
    document.getElementById('next-page').addEventListener('click', () => {
        if (currentPage < totalPages - 1) loadPage(currentPage + 1, 0);
    });
    
    // Direct Page Jump
    const pageInput = document.getElementById('page-input');
    pageInput.addEventListener('change', (e) => {
        let targetPage = parseInt(e.target.value) - 1; // 0-indexed
        if (isNaN(targetPage)) return;
        if (targetPage < 0) targetPage = 0;
        if (targetPage >= totalPages) targetPage = totalPages - 1;
        
        e.target.value = targetPage + 1; // Correct the input value if out of bounds
        if (targetPage !== currentPage) {
            loadPage(targetPage, 0);
        }
    });

    async function loadPage(page, startIdx = 0) {
        if (!currentBook) return;
        bufferStatus.innerText = "Loading page...";
        try {
            const res = await fetch(`/api/book/${currentBook}/page/${page}`);
            const data = await res.json();
            sentences = data.sentences;
            totalPages = data.total_pages; // Update from server
            currentPage = page;
            prefetchedPage = null; // reset background cache
            
            // Clear Audio
            stopAudio();
            
            document.getElementById('page-input').value = page + 1;
            document.getElementById('total-pages').innerText = totalPages;
            document.getElementById('current-title').innerText = currentBook;
            pageControls.classList.remove('hidden');
            
            // Sync native PDF viewer page only if it's currently visible to avoid Chrome StreamContainer crash
            if (showPdf) {
                const encodedBook = encodeURIComponent(currentBook).replace(/\(/g, '%28').replace(/\)/g, '%29');
                pdfFrame.src = `/pdf-file/${encodedBook}#page=${page + 1}`;
            }
            
            renderSentences();
            setIndex(startIdx);
        } catch (err) {
            console.error(err);
            bufferStatus.innerText = "Load failed";
        }
    }

    // Background caching of next page
    async function backgroundCacheNextPage() {
        if (isFetchingNextPage || prefetchedPage || !currentBook || currentPage >= totalPages - 1) return;
        isFetchingNextPage = true;
        try {
            const res = await fetch(`/api/book/${currentBook}/page/${currentPage + 1}`);
            const data = await res.json();
            prefetchedPage = data.sentences;
            
            // Immediately transition and fetch next so sentences array grows and prefetcher can chew it
            transitionToNextPage();
        } catch(e) {
            console.error("Prefetch failed", e);
        } finally {
            isFetchingNextPage = false;
        }
    }

    // Transition to next page seamlessly
    function transitionToNextPage() {
        if (!prefetchedPage) return false;
        
        // Append cache to sentences
        const oldLength = sentences.length;
        sentences = sentences.concat(prefetchedPage);
        
        // Append to DOM
        prefetchedPage.forEach((s, i) => {
            const globalIdx = oldLength + i;
            const span = document.createElement('span');
            span.className = 'sentence';
            if (s.is_new_paragraph) span.classList.add('paragraph-gap');
            span.innerText = s.text;
            span.id = `s-${globalIdx}`;
            span.addEventListener('click', () => setIndex(globalIdx));
            textContainer.appendChild(span);
        });
        
        currentPage++;
        document.getElementById('page-input').value = currentPage + 1;
        document.getElementById('total-pages').innerText = totalPages;
        if (showPdf) {
            const encodedBook = encodeURIComponent(currentBook).replace(/\(/g, '%28').replace(/\)/g, '%29');
            pdfFrame.src = `/pdf-file/${encodedBook}#page=${currentPage + 1}`;
        }
        prefetchedPage = null; // Clear so we can fetch next later
        return true;
    }

    // Render text
    function renderSentences() {
        textContainer.innerHTML = '';
        sentences.forEach((s, i) => {
            const span = document.createElement('span');
            span.className = 'sentence';
            if (s.is_new_paragraph) span.classList.add('paragraph-gap');
            span.innerText = s.text;
            span.id = `s-${i}`;
            span.addEventListener('click', () => setIndex(i));
            textContainer.appendChild(span);
        });
        bufferStatus.innerText = "Ready";
    }

    // Core Logic
    async function setIndex(idx) {
        if (idx < 0 || idx >= sentences.length) return;
        
        // Remove active class from old
        if (currentIndex >= 0 && currentIndex < sentences.length) {
            document.getElementById(`s-${currentIndex}`)?.classList.remove('active');
        }
        
        currentIndex = idx;
        const activeSpan = document.getElementById(`s-${currentIndex}`);
        if (activeSpan && !showPdf) {
            activeSpan.classList.add('active');
            activeSpan.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else if (activeSpan) {
            activeSpan.classList.add('active'); // Still highlight under the hood
        }
        
        saveState();
        
        if (isPlaying || isPreparing) {
            await tryStartPlayback();
        }
    }

    async function ensureBuffer() {
        // Calculate how many sentences are left
        const remaining = sentences.length - currentIndex;
        const targetBuffer = Math.min(REQUIRED_BUFFER_AHEAD, remaining);
        
        let allReady = true;
        for (let i = 0; i < targetBuffer; i++) {
            const idx = currentIndex + i;
            if (!audioCache[idx]) {
                allReady = false;
                // Kick off synthesis if not already synthesizing
                if(!isSynthesizing[idx]) {
                    bufferAudio(idx);
                }
            }
        }
        return allReady;
    }

    async function tryStartPlayback() {
        if (currentIndex < 0 || currentIndex >= sentences.length) {
            pauseAudio();
            return;
        }

        audioPlayer.pause();
        isPreparing = true;
        updatePlayIcon(true);
        bufferStatus.innerText = "Preparing...";

        // Wait until buffer is ready
        while (isPreparing) {
            const ready = await ensureBuffer();
            if (ready) break;
            await new Promise(r => setTimeout(r, 200));
        }

        if (!isPreparing && !isPlaying) return; // Aborted

        isPreparing = false;
        isPlaying = true;
        
        const url = audioCache[currentIndex];
        if (!url) {
            bufferStatus.innerText = "Error playing";
            isPlaying = false;
            return;
        }
        
        audioPlayer.src = url;
        audioPlayer.playbackRate = parseFloat(speedSlider.value) / currentNativeSpeed;
        audioPlayer.volume = volSlider.value;
        
        try {
            await audioPlayer.play();
            bufferStatus.innerText = "Playing";
            stopBtn.classList.remove('hidden'); // Show stop button
        } catch (e) {
            console.error(e);
            pauseAudio();
        }
        
        // Background cache logic
        if (mode === 'pdf' && currentIndex >= sentences.length - 10) {
            backgroundCacheNextPage();
        }
    }

    // Unbounded Prefetch Loop
    async function prefetchLoop() {
        if (!currentBook || mode !== 'pdf' || !isPlaying) return;
        
        // Find how many sentences ahead are currently queued or ready
        const targetIdx = currentIndex + PREFETCH_LIMIT;
        const limit = Math.min(targetIdx, sentences.length);
        
        for (let i = currentIndex; i < limit; i++) {
            if (!audioCache[i] && !isSynthesizing[i]) {
                bufferAudio(i);
            }
        }
        
        // Fetch next pages continuously to keep the sentences array full
        if (sentences.length - currentIndex < PREFETCH_LIMIT) {
            backgroundCacheNextPage();
        }
    }
    
    // Periodically run prefetch
    setInterval(prefetchLoop, 1000);

    // Request Synthesis
    async function bufferAudio(idx) {
        if (idx < 0 || idx >= sentences.length) return null;
        if (audioCache[idx] || isSynthesizing[idx]) return;
        
        isSynthesizing[idx] = true;
        const key = `${currentBook}_p${currentPage}_s${idx}`.replace(/[^a-zA-Z0-9_]/g, '_');
        try {
            await fetch('/api/enqueue_text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    text: sentences[idx].text, 
                    key: key,
                    speed: 1.5 // Native speed
                })
            });
            
            // Start polling
            pollAudio(idx, key);
        } catch (err) {
            console.error("Synth enqueue failed", err);
            isSynthesizing[idx] = false;
        }
    }
    
    async function pollAudio(idx, key) {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/api/check_audio/${key}`);
                const data = await res.json();
                
                if (data.status === 'ready') {
                    audioCache[idx] = data.audio_url;
                    isSynthesizing[idx] = false;
                    clearInterval(interval);
                } else if (data.status === 'error' || data.status === 'not_found') {
                    isSynthesizing[idx] = false;
                    clearInterval(interval);
                }
            } catch(e) {
                isSynthesizing[idx] = false;
                clearInterval(interval);
            }
        }, 1000);
    }

    // Cleanup Audio
    async function cleanupAudio(url) {
        if (!url) return;
        const filename = url.split('/').pop();
        try {
            await fetch(`/api/delete_audio/${filename}`, { method: 'DELETE' });
        } catch (e) {}
    }

    // Stop Everything
    async function stopAudio() {
        pauseAudio();
        stopBtn.classList.add('hidden');
        
        // Don't reset currentIndex = 0 here, so we remember where we stopped
        
        if (sentences.length > 0) {
            // No need to reset active class to sentence 0
        }
        
        bufferStatus.innerText = "Stopped & Cleared";
        
        audioCache = {};
        isSynthesizing = {};
        isPreparing = false;
        
        try {
            await fetch('/api/clear_queue', { method: 'POST' });
            await fetch('/api/cleanup_all', { method: 'POST' });
        } catch(e) {}
    }

    // Events
    audioPlayer.addEventListener('ended', async () => {
        cleanupAudio(audioCache[currentIndex]);
        
        if (isContinuous) {
            if (currentIndex < sentences.length - 1) {
                setIndex(currentIndex + 1);
            } else if (mode === 'pdf') {
                const swapped = transitionToNextPage();
                if (swapped) {
                    setIndex(currentIndex + 1);
                } else {
                    pauseAudio();
                    bufferStatus.innerText = "Finished";
                }
            } else {
                pauseAudio();
                bufferStatus.innerText = "Finished";
            }
        } else {
            pauseAudio();
        }
    });

    playPauseBtn.addEventListener('click', () => {
        if (sentences.length === 0) return;
        if (isPlaying || isPreparing) pauseAudio();
        else {
            if (currentIndex === -1) currentIndex = 0;
            tryStartPlayback();
        }
    });

    stopBtn.addEventListener('click', stopAudio);

    function pauseAudio() {
        isPlaying = false;
        isPreparing = false;
        audioPlayer.pause();
        updatePlayIcon(false);
        if(bufferStatus.innerText !== "Stopped & Cleared") bufferStatus.innerText = "Paused";
    }

    function updatePlayIcon(playing) {
        if (playing) playIcon.className = 'fa-solid fa-pause';
        else playIcon.className = 'fa-solid fa-play';
    }

    prevBtn.addEventListener('click', () => { if (currentIndex > 0) setIndex(currentIndex - 1); });
    nextBtn.addEventListener('click', () => { if (currentIndex < sentences.length - 1) setIndex(currentIndex + 1); });

    // Cleanup on window close
    window.addEventListener('beforeunload', () => {
        navigator.sendBeacon('/api/cleanup_all');
    });

    // Boot
    async function init() {
        initLibrary();
        try {
            const res = await fetch('/api/get_models');
            const data = await res.json();
            currentNativeSpeed = data.native_speed || 1.0;
            modelToggleContainer.innerHTML = '';
            data.models.forEach(m => {
                const radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = 'tts-model';
                radio.id = `model-${m}`;
                radio.value = m;
                if (m === data.active) radio.checked = true;
                
                const label = document.createElement('label');
                label.htmlFor = `model-${m}`;
                label.innerText = m.toUpperCase();
                
                modelToggleContainer.appendChild(radio);
                modelToggleContainer.appendChild(label);
            });
        } catch(e) {}
    }
    
    init();
});
