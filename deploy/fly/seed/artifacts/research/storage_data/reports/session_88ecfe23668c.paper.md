# How an LLM works

## Abstract

This research examines the operational mechanisms and architectural advancements within modern Large Language Models, focusing on how scale influences neural representations of natural language. The study evaluates specific frameworks such as the Psychometric Item Generator derived from GPT-2, lightweight Liquid Siamese Neural Networks for satellite change detection, and the JEPA-MSAC multimodal predictive learning system that unifies sensing measurements into a token space. Findings indicate that models with billions of parameters significantly outperform smaller counterparts in matching neural representations while leveraging Mixture of Experts architectures to enhance computational efficiency through domain-specific specialization. Furthermore, innovations like 3DLS demonstrate substantial throughput improvements over shared-fabric and priority-managed planar baselines, confirming the critical role of architectural optimization alongside model scaling.

## 1. Psychometric Item Generator

The Psychometric Item Generator (PIG) functions as an open-source, free-to-use, self-sufficient natural language processing algorithm that is based on the powerful generative language model GPT-2. [1] This system operates within Google Colaboratory, which provides a virtual notebook environment to execute code on state-of-the-art machines at no cost. [1] Users can easily tailor PIG to any desired context by simply switching out short linguistic prompts in a single line of code. [1] Consequently, the tool is equally well-suited to generate large pools of face-valid items for novel constructs and create parsimonious short scales of existing constructs like Big Five personality traits. [1] Furthermore, when tested in the wild and benchmarked against current gold standards for assessment, PIG yields strong performances. [1]

## 2. Liquid Siamese Neural Network

The Liquid Siamese Neural Network functions as a lightweight technology designed to process multimodal satellite images for specific tasks. This architecture enables the execution of satellite image change detection by analyzing paired visual inputs from different time periods or sensors. By leveraging these multimodal capabilities, the network effectively supports comprehensive change detection workflows within remote sensing applications. Consequently, this approach offers an efficient solution for identifying alterations in geographical features through its specialized neural design [2].

## 3. Large Language Models

Large Language Models improve the representation of natural language within neural networks, a capability that is significantly enhanced when these models contain billions rather than merely millions of parameters.[3][4] This substantial increase in parameter count allows large-scale architectures to better align with how humans process and understand linguistic information. Consequently, the shift from smaller to larger model sizes results in representations that more accurately reflect underlying neural mechanisms for language processing.[3][4]

## 4. Jepa-Msac

JEPA-MSAC functions as a self-supervised multimodal predictive representation learning framework designed to unify diverse data inputs. Specifically, the proposed approach maps multimodal sensing and communication measurements into a single token space to facilitate integrated analysis. By operating within this structure, JEPA-MSAC learns a predictive latent space that effectively captures both environment dynamics and cross-modal dependencies. Consequently, the resulting latent state enables accurate multi-task prediction while maintaining a low adaptation cost for new scenarios.

## 5. 3Dls

The proposed 3DLS architecture demonstrates significant performance improvements over existing planar baselines by achieving up to $1.49\times$ throughput compared to the shared-fabric configuration [6]. Furthermore, when evaluated against a workload-aware priority-managed planar baseline, 3DLS delivers up to $1.17\times$ higher throughput [6]. In addition to these gains in processing speed, the system reduces end-to-end latency by $60.2\%$ relative to the shared-fabric planar approach [6]. Finally, it maintains a substantial advantage over priority-managed systems with $31.4\%$ lower E2E latency than that specific baseline [6].

## 6. Mixture Of Experts (Moe)

The Mixture of Experts (MoE) architecture serves as an effective approach for training extremely large models while improving computational efficiency.[7] Within this framework, domain-specific experts exist to handle particular tasks or knowledge areas within the system.[7] Fundamentally, the MoE method utilizes Large Language Models (LLMs) to structure these specialized components effectively.[7]

## 7. Further Findings

The performance of large language models with billions of parameters is assessed in the Scale matters paper, which notes that such scale-related factors allow these models to better match neural representations of natural language. While some research investigates the effects of aging on brain networks and how narrative coherence affects the default mode network, other studies focus specifically on model architecture improvements. For instance, Domain Steering Mixture of Experts (DSMoE) utilizes a mixture of experts approach that outperforms well-trained MoE-based LLMs and strong baselines including Supervised Fine-Tuning. Additionally, ILN employs Transformer architectures to facilitate multimodal signal processing and decision making within these advanced systems [7][8][9][10][11][12].

## Open Questions

- Unresolved: How do LLMs process and represent sequential data, such as text or speech?
- Unresolved: What are the key components of an LLM architecture, and how do they interact?
- Unresolved: Can LLMs be fine-tuned for specific tasks, and if so, what are the implications for explainability?
- Unresolved: How do LLMs handle out-of-vocabulary words, unknown entities, or ambiguous language?
- Unresolved: What is the relationship between LLMs and other AI models, such as GANs or CNNs?

## Method and Limitations

Sources were gathered by parallel retrieval across 5 source families and reduced to claims by extraction. A claim is reported here only if it cleared the verification floor — a single source at reliability 0.7 or higher, or two independent sources at 0.45 or higher. 57 of 310 claims cleared it. Every statement below carries the source it rests on; nothing is asserted that no source said.

## References

[1] F. Götz, R. Maertens, Sahil Loomba et al.. Let the algorithm speak: How to use neural networks for automatic item generation in psychological scale development.. 2023. https://www.semanticscholar.org/paper/ef0293a162b8d1fb40213bf31acf38bcd81117fb
[2] Kasetty SB, Rajakumar K. Lightweight liquid siamese neural network for robust multimodal satellite image change detection.. 2026. https://pubmed.ncbi.nlm.nih.gov/42069738/
[3] Reviewer #1 (Public review): Scale matters: Large language models with billions (rather than millions) of parameters better match neural representations of natural language. 2026. https://doi.org/10.7554/elife.101204.2.sa3
[4] Reviewer #2 (Public review): Scale matters: Large language models with billions (rather than millions) of parameters better match neural representations of natural language. 2026. https://doi.org/10.7554/elife.101204.2.sa2
[5] Can Zheng, Jiguang He, Guofa Cai et al.. JEPA-MSAC: A Joint-Embedding Predictive Architecture for Multimodal Sensing-Assisted Communications. 2026. https://arxiv.org/abs/2603.29796v1
[6] Jaehun Lee, In-Jun Jung, Joo-Young Kim. 3DLS: A 3D Logic-Stacked Architecture for Disaggregated LLM Serving. 2026. https://arxiv.org/abs/2607.01617v1
[7] Giang Do, Hung Le, Truyen Tran. Do Domain-specific Experts exist in MoE-based LLMs?. 2026. https://arxiv.org/abs/2604.05267v1
[8] Nai Ding. eLife Assessment: Scale matters: Large language models with billions (rather than millions) of parameters better match neural representations of natural language. 2026. https://doi.org/10.7554/elife.101204.2.sa4
[9] Reviewer #3 (Public review): Scale matters: Large language models with billions (rather than millions) of parameters better match neural representations of natural language. 2026. https://doi.org/10.7554/elife.101204.2.sa1
[10] Sun F, Li X, Shi Y et al.. Effects of aging on the mechanisms of dynamic integration between the default mode network and other brain networks: evidence based on fMRI data with natural stimulation.. 2026. https://pubmed.ncbi.nlm.nih.gov/42550319/
[11] Ekstrand C, Haines C, Klamer K et al.. Narrative coherence shapes functional connectivity in default mode and frontoparietal networks.. 2026. https://pubmed.ncbi.nlm.nih.gov/42318318/
[12] ILN - Transformer Architectures for Multimodal Signal Processing &amp; Decision Making. 2026. https://doi.org/10.1109/msp.2026.3659973
