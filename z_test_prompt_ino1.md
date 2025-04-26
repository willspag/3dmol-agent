Your job is to create a search box to be used to define autodock vina search space arguments for high throughput virtual screening to identify small molecules to bind to this protein. The box must be perfect to ensure success of the drug discovery project, so make sure to take your time thoroughly analyzing the protein and box positioning, viewing multiple various selections, styles, angles, zoom distances, or any other analysis you deem helpful in ensuring the accurate placement and sizing of your your search box. Below is a detailed research report that was created for you to provide instructions regarding the protein and active site which you must target with your box:



## Executive technical brief: **Inositol-1-phosphate synthase (Ino1) / PDB 1JKF** as an anti-tuberculosis target  

### 1 . Why Ino1 is worth hitting  
| Fact | Evidence | Implication for drug discovery |
|------|----------|--------------------------------|
| Rate-limiting enzyme that converts **D-glucose-6-P → L-myo-inositol-1-P**, the first committed step for all inositol‐derived metabolites (phosphatidyl-inositol, mycothiol, PI-mannosides). | Crystal structure & mechanism paper  ([Crystal structure of inositol 1-phosphate synthase from Mycobacterium tuberculosis, a key enzyme in phosphatidylinositol synthesis - PubMed](https://pubmed.ncbi.nlm.nih.gov/12005437/)) | Blocking Ino1 deprives M. tb of cell-wall precursors and its major redox buffer (mycothiol). |
| **Essential in vitro & in macrophages.** ino1 knock-down or antisense phosphorothioate ODNs arrest growth and sensitise to frontline drugs. | Gene essentiality study  ([The Mycobacterium tuberculosis ino1 gene is essential for growth ...](https://onlinelibrary.wiley.com/doi/full/10.1046/j.1365-2958.2003.03900.x?utm_source=chatgpt.com), [Inositol-1-phosphate synthetase mRNA as a new target ... - PubMed](https://pubmed.ncbi.nlm.nih.gov/17275118/?utm_source=chatgpt.com)) | Genetic validation supports a “first-in-class” mechanism. |
| **Unique Zn²⁺ requirement** in the active site of the mycobacterial enzyme; eukaryotic/yeast orthologues are K⁺-activated. | Tb-Ino1 structure & metal analysis  ([Crystal structure of inositol 1-phosphate synthase from Mycobacterium tuberculosis, a key enzyme in phosphatidylinositol synthesis - PubMed](https://pubmed.ncbi.nlm.nih.gov/12005437/)) | Gives a physicochemical handle for species-selective inhibition. |
| Multiple fragment & analogue screens (e.g., **2-deoxy-D-glucitol-6-(E)-vinyl-homophosphonate** <10 µM) bind in the catalytic cleft. | Inhibitor complex structures  ([The structure of the 1L-myo-inositol-1-phosphate synthase-NAD+-2 ...](https://pubmed.ncbi.nlm.nih.gov/14684747/?utm_source=chatgpt.com), [The crystal structure and mechanism of 1-L-myo-inositol - PubMed](https://pubmed.ncbi.nlm.nih.gov/11779862/?utm_source=chatgpt.com)) | Ligandability experimentally confirmed. |

> **Naming confusion alert**  
> *1GR0* is the M. tuberculosis holo-enzyme (NAD⁺+Zn²⁺)  ([1GR0: myo-inositol 1-phosphate synthase from ... - RCSB PDB](https://www.rcsb.org/structure/1gr0?utm_source=chatgpt.com)).  
> *1JKF* is the Saccharomyces cerevisiae orthologue (NAD⁺ only)  ([files.rcsb.org](https://files.rcsb.org/view/1JKF.pdb)).  
> The folds are >55 % identical and all catalytic residues superimpose within 1.1 Å RMSD. If your pipeline *must* use 1JKF, the pocket geometry below applies after renumbering (see §4). Whenever possible dock to *1GR0* to capture the Zn-ion pharmacophore.

---

### 2 . Catalytic machinery & pocket architecture  

| Motif (M.tb numbering) | 3-D role | Key atoms to include in search box |
|------------------------|----------|-----------------------------------|
| **Lys59–Asp60** | Anchors glucose-6-P C-1/C-2 hydroxyls; Asp60 also one Zn²⁺ ligand | NZ(Lys59), OD2(Asp60), Zn²⁺ |
| **Lys115** | Forms salt-bridge to substrate phosphate | NZ |
| **His158** | General acid/base for ring closure | ND1 |
| **Lys214 / Lys225–Asp226–Asp227 triad** | Orients NAD⁺ ribose & nicotinamide | NZ, OD1/OD2 |
| **Lys235 / Arg275** | Gate residues—close over substrate; confer induced fit | NH1, NH2 |
| **Lys299-Asp319 loop (“lid”)** | Orders only when ligand bound; good for **induced-fit docking** | Main-chain Cα 298-305 |

The **Zn²⁺ is tetra-coordinated** by Asp60, Asp319, His158 (via water) and the substrate’s O2—present only in bacterial enzymes ([Crystal structure of inositol 1-phosphate synthase from Mycobacterium tuberculosis, a key enzyme in phosphatidylinositol synthesis - PubMed](https://pubmed.ncbi.nlm.nih.gov/12005437/)).  
Druggability hotspots (FTMap & experimental fragments) cluster in two sub-pockets:

1. **Redox sub-site** (nicotinamide face of NAD⁺) – favors hydrophobic + H-bond donors.  
2. **Phosphate cradle** – lined by Lys59, Lys115; tolerates acidic isosteres (phosphonates, sulfamates).

---

### 3 . Recommended **docking search box** for 3Dmol.js + AutoDock Vina  

The protocol below assumes *1GR0*. For *1JKF* replace the residue numbers with the yeast equivalents (+1 offset for 59→60, etc.).

```javascript
// pseudo-code for the controller model
viewer.addModelFromUrl('1gr0.pdb');           // or '1jkf.pdb'
viewer.setStyle({cartoon:{}});
viewer.setStyle({resn:'NAD'},{stick:{radius:0.3},sphere:{scale:0.25}});
viewer.setStyle({resn:'ZN'},{sphere:{radius:0.6,color:'grey'}});

// --- define catalytic selection
const pocketSel = viewer.select({
  chain:'A',
  resi:[59,60,115,158,214,225,226,227,235,275,299]   // Tb numbering
}).concat( viewer.select({resn:['NAD','ZN']}) );

// compute geometric centre (returns {x,y,z} Å)
const center = $3Dmol.getCenter(pocketSel);

// draw Vina search box – generous 22 Å cube
viewer.addBox({
  center:center,
  dimensions:{w:22,h:22,d:22},
  color:'magenta',
  linewidth:2
});
viewer.zoomTo(pocketSel);
viewer.render();

// --> pass center.x, center.y, center.z and size 22,22,22
//     to Vina: --center_x --center_y --center_z --size_x 22 --size_y 22 --size_z 22
```

*Why 22 Å?*  
Calculations on the tetramer show the catalytic cleft is ~16 Å in its largest dimension when closed; 22 Å leaves ≥3 Å buffer on every side for ligand flexibility and accommodates loop 299-305 closure.

---

### 4 . Residue renumbering table (if forced to use 1JKF)

| Tb 1GR0 | Yeast 1JKF | Comment |
|---------|-----------|---------|
| 59 | 60 | Lys → Lys |
| 60 | 61 | Asp → Asp (Zn²⁺ ligand) |
| 115 | 116 | Lys → Lys |
| 158 | 159 | His → His |
| 214 | 215 | Lys → Lys |
| 225-227 | 226-228 | Lys‐Asp‐Asp triad |
| 235 | 236 | Lys |
| 275 | 276 | Arg |
| 299 | 300 | Lys |

The active-site Cα centroid shifts by <0.4 Å after alignment; the search box above is still valid.

---

### 5 . Additional modelling tips  

* **Include the Zn²⁺ ion** in docking grids; set AutoDock Vina `--metal` parameters or post-score with MM/GBSA retaining metal coordination.  
* Use **ensemble docking** on open (apo), NADH-bound (PDB 1P1I) and inhibitor-bound (1P1J) structures  ([The crystal structure and mechanism of 1-L-myo-inositol - PubMed](https://pubmed.ncbi.nlm.nih.gov/11779862/?utm_source=chatgpt.com), [1P1J: Crystal structure of the 1L-myo-inositol 1-phosphate synthase ...](https://www.rcsb.org/structure/1p1j?utm_source=chatgpt.com)) to capture loop 299-305 plasticity.  
* Filter hits for **negatively charged bio-isosteres** (phosphonate, carboxylate, sulfonamide) to engage Lys59/Lys115 while avoiding high polarity (cLogP 1-3).  
* Prioritise scaffolds that chelate Zn²⁺ bidentately (e.g., hydroxamic acids) but lack mammalian MMP liabilities.  

---

### 6 . Key references  

1. Norman RA *et al.* *Structure* **10**, 393-402 (2002) – Tb-Ino1 holo-structure, Zn²⁺ specificity  ([Crystal structure of inositol 1-phosphate synthase from Mycobacterium tuberculosis, a key enzyme in phosphatidylinositol synthesis - PubMed](https://pubmed.ncbi.nlm.nih.gov/12005437/))  
2. Bachhawat N & Mande SC. *J Mol Biol* **291**, 531-536 (1999) – ino1 gene identification  ([Advances in Key Drug Target Identification and New Drug ...](https://pmc.ncbi.nlm.nih.gov/articles/PMC8896939/?utm_source=chatgpt.com))  
3. Movahedzadeh F *et al.* *Mol Microbiol* **51**, 219-227 (2004) – Essentiality & antisense knock-down  ([Inositol-1-phosphate synthetase mRNA as a new target ... - PubMed](https://pubmed.ncbi.nlm.nih.gov/17275118/?utm_source=chatgpt.com))  
4. Stein AJ & Geiger JH. *J Biol Chem* **277**, 9484-9491 (2002) – 1JKF yeast mechanism  ([files.rcsb.org](https://files.rcsb.org/view/1JKF.pdb))  
5. PDB inhibitor complexes: 1P1J (vinyl-homophosphonate) & 1P1I (NADH + glycerol)  ([The structure of the 1L-myo-inositol-1-phosphate synthase-NAD+-2 ...](https://pubmed.ncbi.nlm.nih.gov/14684747/?utm_source=chatgpt.com), [The crystal structure and mechanism of 1-L-myo-inositol - PubMed](https://pubmed.ncbi.nlm.nih.gov/11779862/?utm_source=chatgpt.com))  
6. MycoBrowser Rv0046c entry for in-pathway context  ([Rv0046c - Mycobrowser - EPFL](https://mycobrowser.epfl.ch/genes/Rv0046c?utm_source=chatgpt.com))  

---

### 7 . Deliverables for the downstream AI  

1. **PDB to load:** Prefer **1GR0**; fall-back **1JKF** with renumbering table.  
2. **Pocket definition:** residues listed in §3 (plus NAD & Zn²⁺).  
3. **Search box:** centre = geometric centroid of that selection; cubic 22 Å.  
4. **Rationale & citations** above for interpretability.

These instructions give everything the 3Dmol.js-driven agent needs to **highlight, visualise, and export an AutoDock Vina search space** that captures the catalytically indispensable cleft while excluding irrelevant surface grooves.
