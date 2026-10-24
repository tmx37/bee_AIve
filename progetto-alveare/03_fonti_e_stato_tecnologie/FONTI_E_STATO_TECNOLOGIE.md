# Fonti e stato delle tecnologie

**Progetto Alveare – rete aperta di modelli IA specializzati**
Aggiornato a ottobre 2026. Raccoglie le fonti usate nelle analisi e valuta, per ogni area, quanto la
tecnologia è pronta per il progetto.

**Legenda della maturità**

- **Pronta** – in uso reale, documentata, utilizzabile subito nel prototipo.
- **Utilizzabile** – funziona, ma con limiti noti o integrazione da fare.
- **Sperimentale** – risultati di ricerca o progetti giovani: da provare, non da cui dipendere.
- **Lacuna** – manca una soluzione matura; il progetto deve costruirla o aggirarla.

---

## Sintesi

| Area | Maturità | Tecnologie di riferimento |
|---|---|---|
| Esecuzione locale dei modelli | Pronta | llama.cpp, llama-swap, MLX |
| Modelli piccoli aperti per testo, traduzione, voce | Pronta | famiglie Qwen piccole, SmolLM3, Olmo 3, Hy-MT2, Kokoro, Whisper |
| Modelli di immagini a licenza aperta e loro compressione | Utilizzabile | FLUX.2 klein 4B, Qwen-Image-2512, Z-Image; SVDQuant/Nunchaku |
| Inferenza distribuita su più dispositivi di casa | Utilizzabile | prima.cpp, exo |
| Scomposizione ed esecuzione parallela dei compiti | Utilizzabile | LLMCompiler; standard MCP e A2A |
| Router piccoli con confidenza | Utilizzabile | Needle (esempio); calibrazione isotonica |
| Fine-tuning su hardware domestico | Pronta | Unsloth (QLoRA), ai-toolkit, MLX distribuito |
| Training e validazione collaborativi | Utilizzabile/Sperimentale | Gradients, Templar/Gauntlet, Gensyn SAPO, Flower |
| Firma e verifica dei modelli | Pronta | OpenSSF Model Signing, firme Ed25519 |
| Verifica dei risultati di nodi non fidati | Sperimentale per LLM, Lacuna per diffusion | TOPLOC |
| Compressione estrema (1–2 bit) | Sperimentale | BitNet b1.58, QAT ternario, AngelSlim |
| LLM a diffusione | Sperimentale | DiffusionGemma, LLaDA 2.0, Fast-dLLM |
| Launcher e distribuzione per non tecnici | Utilizzabile | Pinokio (modello di riferimento) |
| Valutazione privata e federata nei tornei | Lacuna | da costruire (prototipo: `alveare validate`) |

---

## 1. Esecuzione locale dei modelli

**Maturità: Pronta.**

- **llama-swap** – proxy leggero (un binario e un file YAML) che espone un unico endpoint
  OpenAI-compatibile e avvia il server giusto in base al modello richiesto; supporta tempo di inattività
  per scaricare i modelli e profili per tenerne più d'uno attivo. Carica anche Whisper e stable-diffusion.cpp.
  Riferimenti: <https://www.sourcepulse.org/projects/1775233>, <https://glukhov.org/it/llm-hosting/llama-swap/>.

- **llama.cpp** – include anche una modalità router per gestire più modelli GGUF senza proxy separato
  (stessa fonte).

- **Raspberry Pi 5** – un modello da 1B (Gemma 3 1B) genera circa 10 token/s su un Pi 5 da 8 GB; in sola CPU
  ci si aspetta 5–15 token/s per modelli da 1,5B e 2–5 per modelli da 3B. Consumo: circa 3 W a riposo e fino
  a 8,8 W a pieno carico.
  Riferimenti: <https://www.kunalganglani.com/blog/gemma-3-raspberry-pi-5-benchmark.md>,
  <https://tinyweights.dev/posts/run-llms-raspberry-pi-5/>,
  <https://raspberry.tips/en/faq/raspberry-pi-power-consumption-update-2026-all-models-compared>.

- **Cactus engine** – motore MIT per dispositivi mobili; inferenza ibrida, modelli personalizzati e parte
  dell'accelerazione hardware sono a pagamento. Riferimento: <https://cactuscompute.com/docs/v1.6>.

**Implicazione per il progetto.** Il prototipo parla con i backend solo via API OpenAI-compatibile, così
llama-server, llama-swap e vLLM restano intercambiabili.

---

## 2. Modelli aperti per i compiti del progetto

**Maturità: Pronta per testo, traduzione e voce; Utilizzabile per immagini.**

**Testo – modelli completamente aperti (pesi, dati e codice)**

- **Olmo 3** (7B e 32B), con catena di addestramento tracciabile fino ai dati.
  <https://arxiv.org/html/2512.13961v2>

- **SmolLM3-3B**, Apache-2.0, con miscela di dati pubblica.
  <https://www.bentoml.com/blog/the-best-open-source-small-language-models>

- **Apertus** (8B, 70B), dati aperti e oltre 1.800 lingue; i pesi della versione 1.5 sono ad accesso controllato.
  <https://huggingface.co/swiss-ai/Apertus-70B-2509>, <https://huggingface.co/HackApertus>

**Traduzione**

- **Hy-MT2** (Tencent): Apache-2.0, taglie 1,8B, 7B e 30B-A3B, 33 lingue; la versione da 1,8B compressa a
  1,25 bit pesa circa 440 MB. <https://www.orcarouter.ai/blog/north-small-translate-1-0-vs-tencent-hy-mt2>

**Voce**

- **Kokoro** (82M parametri, Apache-2.0, supporta l'italiano). <https://github.com/hexgrad/kokoro>
- **Whisper / whisper.cpp** (MIT), gira fino al Raspberry Pi. <https://d-central.tech/fr/modeles-ia-vocale-locale/>

**Immagini e editing** – le licenze variano anche nella stessa famiglia:

- Apache-2.0: FLUX.2 [klein] 4B, Qwen-Image-2512, Z-Image, Qwen-Image-Edit-2509.
- Non commerciali: FLUX.2 [dev], FLUX.2 [klein] 9B, Qwen-Image-2.1 (passato da Apache-2.0 a licenza di sola ricerca).
  <https://github.com/black-forest-labs/flux2/wiki>, <https://vdf.ai/blog/best-local-image-generation-models/>,
  <https://pinggy.io/blog/best_free_open_source_ai_image_generators_to_self_host/>

- **Mobile**: SnapGen++ genera immagini 1024×1024 in circa 1,8 s su iPhone 16 Pro Max in 4 passi.
  <https://the-decoder.com/snaps-snapgen-generates-high-resolution-ai-images-on-iphone-in-under-two-seconds/>

**Evidenze sui modelli piccoli specializzati**

- Un modello sotto il miliardo di parametri, fine-tunato, supera modelli di frontiera usati senza esempi su
  nove benchmark di estrazione di relazioni. <https://arxiv.org/html/2606.22606v1>

- Un modello Qwen3.5 da 0,8B è in produzione al posto di modelli di frontiera per annotare la grammatica.
  <https://arxiv.org/pdf/2610.10827>

- Limite: nel coding reale i modelli piccoli fine-tunati restano molto sotto la frontiera.
  <https://newsletter.systemdesign.one/p/fine-tuning-small-language-models>

**Implicazione.** Accettare solo licenze OSI, fissare le versioni e archiviare i pesi: le licenze cambiano.

---

## 3. Inferenza distribuita su dispositivi di casa

**Maturità: Utilizzabile.**

- **prima.cpp** (ICLR 2026, MIT): modelli da 30–70B su gruppi di dispositivi domestici eterogenei, anche in
  Wi-Fi; 70B a circa 674 ms per token su quattro dispositivi, 32B a 26 token/s con decoding speculativo;
  latenza per token 5–17 volte più bassa di llama.cpp, exo e dllama.
  <https://arxiv.org/abs/2504.08791>, <https://github.com/OpenCPIL/prima.cpp>

- **exo**: dispositivi alla pari, scoperta automatica, suddivisione del modello in base alla topologia;
  percorso migliore oggi sui Mac (MLX). <https://github.com/exo-explore/exo>

**Implicazione.** Dividere un modello su più macchine serve dentro una LAN per far stare modelli grandi; tra
reti diverse conviene parallelizzare per compito.

---

## 4. Scomposizione dei compiti, standard e router

**Maturità: Utilizzabile.**

- **LLMCompiler** (ICML 2024): pianificatore che costruisce un grafo di chiamate, smistamento ed esecuzione
  parallela; fino a 3,7× meno latenza e 6,7× meno costo rispetto a ReAct, anche con modelli aperti.
  <https://arxiv.org/abs/2312.04511v2>

- **MCP e A2A** sotto la governance neutrale dell'Agentic AI Foundation (Linux Foundation); le agent card A2A
  descrivono capacità e connessione di un agente.
  <https://www.ai.engineer/orgs/agentic-ai-foundation>,
  <https://mcp.directory/blog/mcp-foundation-linux-foundation-aaif-2026-explained>

- **Needle** (Cactus Compute) come esempio di router piccolissimo: 29–121M parametri, binario da 8–29 MB,
  pesi Apache-2.0, chiamate a strumenti con confidenza calibrata. Limiti: niente testo libero, al massimo
  5 strumenti per turno, confidenza assente dopo il fine-tuning locale, poco affidabile fuori dall'inglese.
  <https://cactuscompute.com/needle>, <https://cactuscompute.com/blog/needle-confidence>,
  <https://cactuscompute.com/blog/finetuning-needle>, <https://pypi.org/project/needle-rs/0.3.0/>

- **Calibrazione della confidenza**: una regressione isotonica su un set di validazione ha ridotto l'errore
  di calibrazione da 0,12 a 0,03 in un caso di produzione. <https://arxiv.org/pdf/2605.18796>

- **OpenLLM (openllm.sh)**: buona idea di catene di riserva e dispositivi in rete, ma licenza Business Source
  1.1, non open source OSI. <https://glama.ai/mcp/servers/openllmsh/cli>

---

## 5. Supporto alla conoscenza: indici, grafi, mappe

**Maturità: Utilizzabile.**

- **PageIndex**: indice gerarchico navigato dal modello, 98,7% su FinanceBench; richiede un modello capace
  di ragionare. <https://pyshine.com/PageIndex-Vectorless-Reasoning-RAG/>

- **LightRAG** (indice a grafo, recupero a due livelli) <https://arxiv.org/pdf/2410.05779> e **MiniRAG**
  (pensato per modelli piccoli, circa 25% dello spazio) <https://www.emergentmind.com/topics/minirag>.

---

## 6. Compressione

**Maturità: Pronta a 4 bit; Sperimentale sotto i 2 bit.**

- **SVDQuant / Nunchaku**: diffusion a 4 bit; FLUX.1-dev occupa 3,6 volte meno memoria e su un laptop con
  16 GB di GPU va fino a 8,7 volte più veloce; Qwen-Image scende a circa 3 GB di VRAM.
  <https://arxiv.org/abs/2411.05007>, <https://github.com/nunchux-ai/nunchaku>

- **Distillazione a pochi passi**: un LCM a 2–4 passi richiede circa 32 ore di A100; LCM-LoRA si applica a
  modelli già personalizzati e si combina con adattatori di stile.
  <https://www.arxiv-vanity.com/papers/2311.05556>

- **BitNet b1.58**: pesi ternari; il modello 2B4T è stato addestrato da zero su 4.000 miliardi di token
  (fuori portata per una community); bitnet.cpp accelera l'inferenza su CPU.
  <https://labs.ai.azure.com/innovations/bitnet/>, <https://github.com/microsoft/BitNet>

- **QAT ternario su piccola scala**: un modello di embedding a 1,58 bit mantiene circa il 95% della qualità
  e sta in 7 MB. <https://huggingface.co/wenshutang/ternlight>

---

## 7. LLM a diffusione

**Maturità: Sperimentale.**

- DiffusionGemma (Apache-2.0, giugno 2026) e LLaDA 2.0 (16B e 100B, pesi aperti).
  <https://zylos.ai/research/2026-06-16-diffusion-language-models-agentic-inference/>

- Fast-dLLM: fino a 27,6 volte più throughput su LLaDA e Dream. <https://nvlabs.github.io/Fast-dLLM/>
- Fast-dLLM v2 converte un modello autoregressivo in uno a diffusione con circa un miliardo di token di
  fine-tuning. <https://buzzgrewal.medium.com/beyond-next-token-how-diffusion-llms-like-mercury-2-and-llada-hit-1-000-tokens-per-second-in-2026-996b52cd4fce>

---

## 8. Training su hardware domestico

**Maturità: Pronta.**

- **Unsloth**: QLoRA di un modello da 8B in circa 6 GB di VRAM, da 3B in circa 3,5 GB.
  <https://docs.unsloth.ai/get-started/beginner-start-here/unsloth-requirements>

- **Adattatori per immagini**: AI Toolkit chiede almeno 24 GB per FLUX e Qwen-Image, 32 GB o più per i
  modelli di editing; con pesi FP8 bastano 12 GB e 3–5 ore per 20–50 immagini.
  <https://www.runcomfy.com/trainer/ai-toolkit/getting-started>,
  <https://www.promptus.ai/workflow/how-to-train-lora-models-with-flux-in-comfyui>

- **Più Mac insieme**: mlx_lm.lora supporta il fine-tuning distribuito; su Thunderbolt circa 20 Gbps effettivi
  per collegamento. <https://developer.apple.com/videos/play/wwdc2026/233/>, <https://arxiv.org/pdf/2609.18066>

---

## 9. Training e validazione collaborativi

**Maturità: Utilizzabile (tornei, federato); Sperimentale (training sincrono via internet).**

- **Gradients** (torneo di fine-tuning): 10–20 partecipanti per modelli linguistici e 15–25 per diffusion,
  valutazione su test segreti; ha battuto TogetherAI, Databricks e Google Cloud nel 100% dei casi e AutoTrain
  nell'82,8%; si appoggia a un validatore principale gestito da Rayon Labs.
  <https://arxiv.org/abs/2506.07940v1>, <https://learnbittensor.org/subnets/56>

- **Templar / Gauntlet**: training permissionless; i validatori misurano quanto ogni contributo riduce l'errore.
  <https://arxiv.org/html/2505.21684v1>

- **Gensyn SAPO / RL Swarm**: apprendimento per rinforzo condiviso tra nodi eterogenei, fino a +94% di
  ricompensa cumulativa; codice MIT. <https://arxiv.org/abs/2509.08721v1>,
  <https://blog.gensyn.ai/rl-swarm-a-framework-for-collaborative-rl/>

- **Rischio di attacchi** nel training decentralizzato documentato dalla stessa Gensyn.
  <https://www.gensyn.ai/research/sapo-efficient-lm-post-training-with-collective-rl>

- **Flower / FlowerTune**: fine-tuning federato con LoRA senza condividere i dati (NeurIPS 2025).
  <https://proceedings.neurips.cc/paper_files/paper/2025/hash/563991b5c8b45fe75bea42db738223b2-Abstract-Datasets_and_Benchmarks_Track.html>

- **Training via internet su larga scala**: INTELLECT-1 (10B su 1.000 miliardi di token)
  <https://arxiv.org/pdf/2412.01152>; anche i modelli più grandi addestrati così hanno usato circa mille volte
  meno calcolo della frontiera <https://epoch.ai/gradient-updates/how-far-can-decentralized-training-over-the-internet-scale>.

**Lacuna.** Non esiste uno standard maturo per la valutazione privata e federata dei candidati: il prototipo
ne implementa una prima versione (rapporto firmato con solo l'hash dei casi di test).

---

## 10. Fiducia e sicurezza

**Maturità: Pronta per la firma dei modelli; Sperimentale per la verifica dei risultati.**

- **OpenSSF Model Signing (OMS)**: supporta Sigstore, certificati auto-firmati o coppie di chiavi con lo
  stesso formato; NVIDIA firma i modelli su NGC da marzo 2025; la variante Sigstore senza chiavi richiede la
  rete. <https://openssf.org/?p=8454>, <https://tianpan.co/blog/2026/07/02/sign-your-weights>,
  <https://pypi.org/project/modelsign/1.0.2/>

- **TOPLOC**: verifica che un nodo non fidato abbia usato il modello, il prompt e la precisione dichiarati,
  con 258 byte di prova ogni 32 token; integrato con vLLM e SGLang.
  <https://primeintellect.ai/blog/toploc>, <https://proceedings.mlr.press/v267/ong25a.html>

**Lacuna.** Per i modelli diffusion non risulta un metodo maturo equivalente: proposta di riesecuzione a
campione con confronto percettivo, da validare.

---

## 11. Community, volontariato, distribuzione

- **AI Horde**: rete non-profit di GPU volontarie per immagini e testo, con crediti non commerciabili; oltre
  135 milioni di richieste testuali evase, ma poche decine di worker attivi in un dato momento.
  <https://stablehorde.net:443>, <https://aihorde.net/contribute/joining>

- **OpenAssistant**: oltre 13.000 volontari, più di 625.000 compiti completati, dati con licenze permissive.
  <https://arxiv.org/pdf/2304.07327>

- **Pinokio**: launcher MIT per installare app di IA in un clic, script JSON/JavaScript con variabili
  sull'hardware rilevato; nessun ricavo. <https://pasqualepillitteri.it/en/news/9050/pinokio-ai-browser-install-guide>,
  <https://thegtmdirectory.com/tools/pinokio>

---

## 12. Dati di mercato e d'uso (analisi delle potenzialità)

| Dato | Valore | Fonte |
|---|---|---|
| Quota di richieste di lavoro che riguardano la scrittura | 40% (due terzi modificano un testo dato) | <https://cdn.openai.com/pdf/a253471f-8260-40c6-a2cc-aa93fe9f142e/economic-research-chatgpt-usage-paper.pdf> |
| Quota di messaggi sulla programmazione | 4,2% | stessa fonte |
| Imprese italiane (≥ 10 addetti) che usano IA | 16,4% nel 2025 | <https://www.istat.it/comunicato-stampa/imprese-e-ict-anno-2025/> |
| Imprese italiane che hanno valutato l'IA senza adottarla | 11,5% | <https://www.assolombarda.it/centro-studi/utilizzo-dellintelligenza-artificiale-nelle-imprese> |
| Barriere tra le imprese UE che hanno valutato l'IA | competenze 70,3%, incertezza legale 53,6%, privacy 52,7% | <https://ai.bcci.bg/en/news/why-companies-that-considered-ai-decided-against-it> |
| Mercato italiano dell'IA | 1,8 miliardi € nel 2025 | <https://www.borsaitaliana.it/borsa/notizie/teleborsa/economia/l-ai-vale-18-miliardi-in-italia-al-via-confronto-alla-camera-su-pmi-e-competenze-103_2026-09-25_TLB.html> |
| Costo orario del lavoro in Italia | 30,9 € (2024) | <https://tg24.sky.it/economia/2025/04/10/lavoro-costo-orario-paesi-ue> |
| Effetto dell'IA generativa sulla produttività | +14% medio, +34% per i meno esperti | <https://www.nber.org/papers/w31161> |
| Prezzi API (per milione di token) | Opus 5.5: 4 $ / 20 $; DeepSeek V4.1 Flash: 0,30 $ / 1,20 $ (punta) | <https://www.gradually.ai/en/llm-comparison/claude-opus-5.5-vs-deepseek-v4.1-flash/> |
| Calo dei prezzi a parità di prestazioni | mediana 50× all'anno, 200× dal 2024 | <https://epoch.ai/data-insights/llm-inference-price-trends> |
| Ritardo dei modelli aperti su GPU consumer rispetto alla frontiera | un anno o meno | <https://epoch.ai/blog/top-10-data-insights-and-gradient-updates-of-2025> |
| PC da gioco con almeno 10 GB di VRAM | 51,4% (luglio 2026) | <https://tbreak.com/steam-hardware-survey-16gb-vram-overtakes-8gb/> |
| Struttura delle imprese italiane | 4,37 milioni di imprese, 94,9% sotto i 10 addetti (dato 2010) | <https://www.istat.it/it/archivio/73481> |

---

## 13. Lacune principali da colmare con il progetto

1. **Valutazione privata e federata** dei candidati nei tornei, resistente alla manipolazione.
2. **Verifica dei risultati dei modelli diffusion** prodotti da nodi non fidati.
3. **Router piccoli affidabili in italiano**, con confidenza calibrata dopo il fine-tuning.
4. **Launcher per non tecnici** che nasconda chiavi, firme e configurazioni.
5. **Incentivi senza token** capaci di mantenere una partecipazione stabile.
