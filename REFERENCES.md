# References & Citations for Pull-Up Planner Core Model

This document lists the scientific publications and evidence-based sources used to design the training formulas, fatigue model, and progression rules in the pull-up planner core engine.

---

## Primary sources (peer-reviewed)

### Rest intervals and hypertrophy/strength

1. **Schoenfeld BJ, Pope ZK, Benik FM, et al.** (2016)  
   *Longer Interset Rest Periods Enhance Muscle Strength and Hypertrophy in Resistance-Trained Men*  
   Journal of Strength and Conditioning Research, 30(7):1805-1812  
   DOI: [10.1519/JSC.0000000000001272](https://doi.org/10.1519/JSC.0000000000001272)  
   PubMed: [26605807](https://pubmed.ncbi.nlm.nih.gov/26605807/)  
   **Key finding**: 3-minute rest intervals produced greater strength and some hypertrophy outcomes compared with 1-minute rest in an 8-week controlled trial.

2. **Refalo MC, Helms ER, Robinson ZP, et al.** (2024)  
   *Give it a rest: a systematic review with Bayesian meta-analysis on the effect of inter-set rest interval duration on muscle hypertrophy*  
   Frontiers in Sports and Active Living, 6:1429789  
   DOI: [10.3389/fspor.2024.1429789](https://doi.org/10.3389/fspor.2024.1429789)  
   **Key finding**: Small hypertrophy benefit for rest intervals >60 s; no appreciable additional difference detected beyond ~90 s in the Bayesian analysis.

### Training frequency

3. **National Strength and Conditioning Association (NSCA)** (2017)  
   *Determination of Resistance Training Frequency*  
   Kinetic Select article  
   URL: [https://www.nsca.com/education/articles/kinetic-select/determination-of-resistance-training-frequency/](https://www.nsca.com/education/articles/kinetic-select/determination-of-resistance-training-frequency/)  
   **Key guidance**: Intermediate trainees often tolerate 3–4 training days per week; recovery between same-movement-pattern sessions is essential.

### Fitness–fatigue impulse-response model

4. **Busso T, Candau R, Lacour JR** (1994)  
   *Fatigue and fitness modelled from the effects of training on performance*  
   European Journal of Applied Physiology, 69:50-54  
   DOI: [10.1007/BF00867927](https://doi.org/10.1007/BF00867927)  
   **Context**: Assessing limitations of the Banister impulse-response model; foundational paper for two-timescale fitness/fatigue modeling.

5. **Calvert TW, Banister EW, Savage MV, Bach T** (1976)  
   *A Systems Model of the Effects of Training on Physical Performance*  
   IEEE Transactions on Systems, Man, and Cybernetics, SMC-6(2):94-102  
   DOI: [10.1109/TSMC.1976.5409179](https://doi.org/10.1109/TSMC.1976.5409179)  
   **Context**: Original Banister model publication introducing impulse-response framework for training adaptation.

6. **Mujika I, Halson S, Burke LM, Balagué G, Farrow D** (2018)  
   *An Integrated, Multifactorial Approach to Periodization for Optimal Performance in Individual and Team Sports*  
   International Journal of Sports Physiology and Performance, 13(5):538-561  
   DOI: [10.1123/ijspp.2018-0093](https://doi.org/10.1123/ijspp.2018-0093)  
   **Context**: Modern review of periodization including fitness-fatigue concepts and practical autoregulation.

7. **Fister I, Fister I Jr, Fister D, Safarič R** (2022)  
   *Continuous optimizers for automatic design and evaluation of classification pipelines*  
   Scientific Reports (fitness-fatigue model review in sports context)  
   PMC: [PMC8894528](https://pmc.ncbi.nlm.nih.gov/articles/PMC8894528/)  
   **Context**: Review of fitness-fatigue models for sport performance modeling.

### Autoregulation and RIR/RPE

8. **Greig L, Aspe RR, Hall A, Comfort P, Swinton PA** (2025)  
   *Exercise type, training load, velocity loss threshold, and sets affect resistance training outcomes and fatigue*  
   Sports Medicine - Open, 11(1):87  
   PMC: [PMC12360324](https://pmc.ncbi.nlm.nih.gov/articles/PMC12360324/)  
   DOI: [10.1186/s40798-025-00830-w](https://doi.org/10.1186/s40798-025-00830-w)  
   **Key finding**: Velocity loss and RIR interact with load and set number; autoregulation should be context-dependent.

### Volume dose-response for hypertrophy

9. **Schoenfeld BJ, Ogborn D, Krieger JW** (2017)  
   *Dose-response relationship between weekly resistance training volume and increases in muscle mass: A systematic review and meta-analysis*  
   Journal of Sports Sciences, 35(11):1073-1082  
   DOI: [10.1080/02640414.2016.1210197](https://doi.org/10.1080/02640414.2016.1210197)  
   **Key finding**: Dose-response relationship exists; higher volumes (to a point) produce greater hypertrophy, but individual variation is high.

10. **Baz-Valle E, Fontes-Villalba M, Santos-Concejero J** (2021)  
    *Total Number of Sets as a Training Volume Quantification Method for Muscle Hypertrophy: A Systematic Review*  
    Journal of Strength and Conditioning Research, 35(3):870-878  
    DOI: [10.1519/JSC.0000000000002776](https://doi.org/10.1519/JSC.0000000000002776)  
    **Context**: Weekly set counts of ~12–24 per muscle group commonly effective, with strong individual variation.

---

## Secondary/Applied sources (evidence-based practitioner guidelines)

11. **Stronger by Science** – Greg Nuckols, Eric Trexler, et al.  
    *Rest Times for Muscle Growth*  
    URL: [https://www.strongerbyscience.com/rest-times-for-muscle-growth/](https://www.strongerbyscience.com/rest-times-for-muscle-growth/)  
    **Summary**: Practical synthesis of rest-interval research for hypertrophy.

12. **Weightology** – James Krieger  
    *Training Frequency for Hypertrophy: The Evidence-Based Bible*  
    URL: [https://weightology.net/the-members-area/evidence-based-guides/training-frequency-for-hypertrophy-the-evidence-based-bible/](https://weightology.net/the-members-area/evidence-based-guides/training-frequency-for-hypertrophy-the-evidence-based-bible/)  
    **Summary**: Evidence synthesis on optimal training frequency per muscle group.

13. **Weightology** – James Krieger  
    *Set Volume for Muscle Size: The Ultimate Evidence Based Bible*  
    URL: [https://weightology.net/the-members-area/evidence-based-guides/set-volume-for-muscle-size-the-ultimate-evidence-based-bible/](https://weightology.net/the-members-area/evidence-based-guides/set-volume-for-muscle-size-the-ultimate-evidence-based-bible/)  
    **Summary**: Comprehensive review of weekly set volume landmarks and individual variation.

---

## How formulas map to sources

| Formula/Rule | Primary source(s) |
|-------------|------------------|
| Rest normalization factor (longer rest → better performance) | [1], [2] |
| 3–4 training days per week default | [3] |
| Fitness–fatigue impulse response (two-timescale exponential decay) | [4], [5], [7] |
| RIR/RPE interpretation and context dependence | [8] |
| Weekly volume targets (12–24 sets range as starting point) | [9], [10], [13] |
| Autoregulation via readiness z-score | [6], [8] |
| Deload frequency and triggers | [6], [12] |

---

## Limitations and caveats

- The Banister fitness-fatigue model is a **simplified abstraction**; individual responses vary widely, and the model requires parameter tuning from logged data.
- Rest-interval effects on hypertrophy show **high individual variability** and interaction with training status, exercise selection, and nutrition.
- Pull-up-specific research is sparse; we extrapolate from general resistance training principles and bodyweight/gymnastic training practice.
- All parameter defaults in `core/config.py` are **starting estimates** and should be adjusted based on observed user outcomes.

---

## Additional reading (not directly cited in formulas)

- **Helms ER, Cronin J, Storey A, Zourdos MC** (2016). *Application of the Repetitions in Reserve-Based Rating of Perceived Exertion Scale for Resistance Training*. Strength and Conditioning Journal, 38(4):42-49.
- **Zourdos MC, Klemp A, Dolan C, et al.** (2016). *Novel Resistance Training–Specific Rating of Perceived Exertion Scale Measuring Repetitions in Reserve*. Journal of Strength and Conditioning Research, 30(1):267-275.
- **TrainingPeaks blog** on Performance Manager Chart (PMC) / Chronic Training Load (CTL) and Acute Training Load (ATL) concepts derived from impulse-response models.

---

