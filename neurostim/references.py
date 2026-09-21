"""Bibliography for every literature-derived constant and equation in this package.

Every numeric constant that did not come from a first-principles derivation carries a
``reference`` key into :data:`REFERENCES`, plus a ``verified`` flag recording whether the
value was read out of the primary source text (``True``) or carried over from secondary
material and still needs checking (``False``).

Fields left empty were not confirmed against the primary source and are deliberately
blank rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

SourceType = str
"""One of ``journal``, ``conference``, ``abstract``, ``unpublished``, ``database``, ``user``.

``abstract`` and ``unpublished`` matter: a value that has not been through peer review
carries less weight than one that has, and the difference should be visible at the point
of use rather than buried in a reference list.
"""

PEER_REVIEWED = frozenset({"journal", "conference"})


@dataclass(frozen=True)
class Reference:
    """A single bibliographic entry."""

    key: str
    authors: str
    title: str
    year: int
    venue: str = ""
    volume: str = ""
    pages: str = ""
    doi: str = ""
    pmid: str = ""
    note: str = ""
    source_type: SourceType = "journal"

    @property
    def peer_reviewed(self) -> bool:
        """Whether this source went through peer review."""
        return self.source_type in PEER_REVIEWED

    def citation(self) -> str:
        """Format as a plain-text citation string."""
        parts = [f"{self.authors} ({self.year}). {self.title}."]
        if self.venue:
            venue = self.venue
            if self.volume:
                venue += f" {self.volume}"
            if self.pages:
                venue += f":{self.pages}"
            parts.append(venue + ".")
        if self.doi:
            parts.append(f"doi:{self.doi}")
        if self.pmid:
            parts.append(f"PMID:{self.pmid}")
        if not self.peer_reviewed and self.source_type != "user":
            parts.append(f"[{self.source_type.upper()} - not peer reviewed]")
        return " ".join(parts)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.citation()


def _ref(**kwargs) -> Reference:
    return Reference(**kwargs)


REFERENCES: dict[str, Reference] = {
    "shannon1992": _ref(
        key="shannon1992",
        authors="Shannon RV",
        title="A model of safe levels for electrical stimulation",
        year=1992,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="39(4)",
        pages="424-426",
        doi="10.1109/10.126616",
        note="Source of the k-metric log(Q/A) = k - log(Q); k fit to McCreery data.",
    ),
    "mccreery1990": _ref(
        key="mccreery1990",
        authors="McCreery DB, Agnew WF, Yuen TGH, Bullara L",
        title=(
            "Charge density and charge per phase as cofactors in neural injury "
            "induced by electrical stimulation"
        ),
        year=1990,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="37(10)",
        pages="996-1001",
        doi="10.1109/10.102812",
        note="Cat parietal cortex damage/no-damage data underlying the Shannon fit.",
    ),
    "merrill2005": _ref(
        key="merrill2005",
        authors="Merrill DR, Bikson M, Jefferys JGR",
        title=(
            "Electrical stimulation of excitable tissue: design of efficacious "
            "and safe protocols"
        ),
        year=2005,
        venue="Journal of Neuroscience Methods",
        volume="141(2)",
        pages="171-198",
        doi="10.1016/j.jneumeth.2004.10.020",
        pmid="15661300",
        note="Shannon eq. (5.1) with 2.0 > k > 1.5; water window definition; Lapicque eq. (4.2).",
    ),
    "cogan2008": _ref(
        key="cogan2008",
        authors="Cogan SF",
        title="Neural stimulation and recording electrodes",
        year=2008,
        venue="Annual Review of Biomedical Engineering",
        volume="10",
        pages="275-309",
        doi="10.1146/annurev.bioeng.10.061807.160518",
        pmid="18429704",
        note="Table 2: charge-injection limits and potential limits for CNS stimulation.",
    ),
    "iso14708_3_2017": _ref(
        key="iso14708_3_2017",
        authors="International Organization for Standardization",
        title=(
            "ISO 14708-3:2017 Implants for surgery -- Active implantable medical "
            "devices -- Part 3: Implantable neurostimulators"
        ),
        year=2017,
        venue="ISO, Geneva",
        source_type="standard",
        note=(
            "Clause 17.1 gives the heat requirement: no outer surface above 39 C, or "
            "no tissue above the Table 101 CEM43 dose thresholds, or manufacturer "
            "justification. Brain threshold is 2 CEM43, twentyfold stricter than "
            "muscle or peripheral nerve."
        ),
    ),
    "kuncel_grill2004_full": _ref(
        key="kuncel_grill2004_full",
        authors="Kuncel AM, Grill WM",
        title="Selection of stimulus parameters for deep brain stimulation",
        year=2004,
        venue="Clinical Neurophysiology",
        volume="115(11)",
        pages="2431-2441",
        doi="10.1016/j.clinph.2004.05.031",
        pmid="15465430",
        note=(
            "States plainly that the 30 uC/cm^2 DBS charge-density limit is a liberal "
            "estimate, and gives three reasons: the source data were collected at "
            "frequencies far below DBS rates, the reassuring post-mortem studies used "
            "charge densities well below the limit, and the limit was derived from "
            "surface-averaged charge density while 25.6 % of a contact operates above "
            "the average current density."
        ),
    ),
    "hudak2017": _ref(
        key="hudak2017",
        authors="Hudak EM, Kumsa DW, Martin HB, Mortimer JT",
        title=(
            "Electron transfer processes occurring on platinum neural stimulating "
            "electrodes: calculated charge-storage capacities are inaccessible during "
            "applied stimulation"
        ),
        year=2017,
        venue="Journal of Neural Engineering",
        volume="14(4)",
        pages="046012",
        doi="10.1088/1741-2552/aa6945",
        note=(
            "Explains mechanistically why charge-storage capacity from cyclic "
            "voltammetry overestimates injectable charge: a cleaned Pt surface reverts "
            "to an obstructed state under stimulation, irreversible oxygen reduction "
            "can occur, and chloride and serum protein inhibit oxide formation and "
            "alter hydrogen adsorption."
        ),
    ),
    "gabriel1996": _ref(
        key="gabriel1996",
        authors="Gabriel C, Gabriel S, Corthout E",
        title="The dielectric properties of biological tissues: I. Literature survey",
        year=1996,
        venue="Physics in Medicine and Biology",
        volume="41(11)",
        pages="2231-2249",
        doi="10.1088/0031-9155/41/11/001",
        pmid="8938024",
        note=(
            "Part I is a graphical survey with no tabulated values; the parametric "
            "Cole-Cole model is in Part III. Useful here for two caveats: dielectric "
            "temperature coefficients run 1-2 %/C at low frequencies and are too "
            "poorly characterised to extrapolate, and grey/white matter are well "
            "studied only above 10 kHz -- above the effective band of a 200 us pulse."
        ),
    ),
    "mccreery2010": _ref(
        key="mccreery2010",
        authors="McCreery D, Pikov V, Troyk PR",
        title=(
            "Neuronal loss due to prolonged controlled-current stimulation with "
            "chronically implanted microelectrodes in the cat cerebral cortex"
        ),
        year=2010,
        venue="Journal of Neural Engineering",
        volume="7(3)",
        pages="036005",
        doi="10.1088/1741-2560/7/3/036005",
        pmid="20460692",
        note=(
            "Primary source for the 4 nC/phase microelectrode figure. 2 nC/phase was "
            "safe and 4 nC/phase damaging, so 4 is the lowest damaging level rather "
            "than the highest safe one. Halving duty cycle shrank the damage radius "
            "from >=150 um to ~60 um at identical charge per phase."
        ),
    ),
    "wang2014_edge": _ref(
        key="wang2014_edge",
        authors="Wang B, Petrossians A, Weiland JD",
        title="Reduction of edge effect on disk electrodes by optimized current waveform",
        year=2014,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="61(8)",
        pages="2254-2263",
        doi="10.1109/TBME.2014.2300860",
        pmid="25051544",
        note=(
            "Shaping the leading edge of the current pulse reduces the edge current "
            "density that drives electrode corrosion and tissue damage. A waveform-level "
            "mitigation for the concentration this package computes geometrically."
        ),
    ),
    "mcintyre_grill2001": _ref(
        key="mcintyre_grill2001",
        authors="McIntyre CC, Grill WM",
        title=(
            "Finite element analysis of the current-density and electric field "
            "generated by metal microelectrodes"
        ),
        year=2001,
        venue="Annals of Biomedical Engineering",
        volume="29(3)",
        pages="227-235",
        doi="10.1114/1.1352640",
        pmid="11310784",
        note=(
            "Current density concentrates at a microelectrode tip. A thin, modestly "
            "conducting surface film makes the distribution markedly more uniform -- the "
            "coating analogue of recessing a disc."
        ),
    ),
    "rubinstein1987": _ref(
        key="rubinstein1987",
        authors="Rubinstein JT, Spelman FA, Soma M, Suesserman MF",
        title=(
            "Current density profiles of surface mounted and recessed electrodes for "
            "neural prostheses"
        ),
        year=1987,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="BME-34(11)",
        pages="864-875",
        doi="10.1109/TBME.1987.325931",
        note=(
            "Green's function solution for a recessed disc, solved by the moment "
            "method with error under 7 %. Recessing gives a more uniform current "
            "density both at the electrode surface and at the carrier-tissue junction, "
            "which is the mitigation for the edge concentration this package computes."
        ),
    ),
    "cui_zhou2007": _ref(
        key="cui_zhou2007",
        authors="Cui XT, Zhou DD",
        title="Poly(3,4-ethylenedioxythiophene) for chronic neural stimulation",
        year=2007,
        venue="IEEE Transactions on Neural Systems and Rehabilitation Engineering",
        volume="15(4)",
        pages="502-508",
        doi="10.1109/TNSRE.2007.909811",
        pmid="18198707",
        note=(
            "Peer-reviewed PEDOT charge-injection limit of 2.3 mC/cm^2 on thin-film Pt, "
            "described as comparable to iridium oxide. Also cites Rose & Robblee as "
            "paper VIII at 37:1118-1120, a third independent confirmation."
        ),
    ),
    "luo2011": _ref(
        key="luo2011",
        authors="Luo X, Weaver CL, Zhou DD, Greenberg R, Cui XT",
        title=(
            "Highly stable carbon nanotube doped poly(3,4-ethylenedioxythiophene) "
            "for chronic neural stimulation"
        ),
        year=2011,
        venue="Biomaterials",
        volume="32(24)",
        pages="5551-5557",
        doi="10.1016/j.biomaterials.2011.04.051",
        pmid="21601278",
        note="PEDOT/CNT charge-injection limit 2.5 +/- 0.1 mC/cm^2 (n = 4).",
    ),
    "leung2014": _ref(
        key="leung2014",
        authors="Leung RT, Shivdasani MN, Nayagam DAX, Shepherd RK",
        title=(
            "In vivo and in vitro comparison of the charge injection capacity of "
            "platinum macroelectrodes"
        ),
        year=2014,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="62(3)",
        pages="849-857",
        doi="10.1109/TBME.2014.2366514",
        pmid="25376031",
        note=(
            "Pt macroelectrode Qinj in vitro 34-54 uC/cm^2 over 100-3200 us, against "
            "3.84-16.6 uC/cm^2 acutely and 6.99-15.8 uC/cm^2 chronically in vivo. No "
            "significant acute-versus-chronic difference."
        ),
    ),
    "hu2006": _ref(
        key="hu2006",
        authors="Hu Z, Troyk PR, Brawn TP, Margoliash D, Cogan SF",
        title="In vitro and in vivo charge capacity of AIROF microelectrodes",
        year=2006,
        venue="Proceedings of the IEEE Engineering in Medicine and Biology Society",
        volume="2006",
        pages="886-889",
        doi="10.1109/IEMBS.2006.259747",
        source_type="conference",
        note=(
            "AIROF in vitro charge density of 3-4 mC/cm^2 is about ten times larger "
            "than what the same films deliver in vivo."
        ),
    ),
    "kane2013": _ref(
        key="kane2013",
        authors="Kane SR, Cogan SF, Ehrlich J, Plante TD, McCreery DB, Troyk PR",
        title=(
            "Electrical performance of penetrating microelectrodes chronically "
            "implanted in cat cortex"
        ),
        year=2013,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="60(8)",
        pages="2153-2160",
        doi="10.1109/TBME.2013.2248152",
        pmid="23475329",
        note=(
            "SIROF microelectrodes chronically implanted in cat cortex. Electrodes "
            "delivering 8 nC/phase in vitro approached or exceeded the water reduction "
            "potential when pulsed in vivo."
        ),
    ),
    "terasawa2013": _ref(
        key="terasawa2013",
        authors="Terasawa Y, Tashiro H, Nakano Y, Osawa K, Ozawa M",
        title=(
            "Safety assessment of semichronic suprachoroidal electrical stimulation "
            "to rabbit retina"
        ),
        year=2013,
        venue="Proceedings of the IEEE Engineering in Medicine and Biology Society",
        volume="2013",
        pages="3567-3570",
        doi="10.1109/EMBC.2013.6610314",
        pmid="24110500",
        source_type="conference",
        note="Porous platinum lost about eightfold charge capacity after ~45 days in vivo.",
    ),
    "gabriel1996_iii": _ref(
        key="gabriel1996_iii",
        authors="Gabriel S, Lau RW, Gabriel C",
        title=(
            "The dielectric properties of biological tissues: III. Parametric models "
            "for the dielectric spectrum of tissues"
        ),
        year=1996,
        venue="Physics in Medicine and Biology",
        volume="41(11)",
        pages="2271-2293",
        doi="10.1088/0031-9155/41/11/003",
        pmid="8938026",
        note=(
            "Four-Cole-Cole parameters, Table 1. Evaluated at the effective frequency "
            "of a 200 us pulse this gives grey matter 0.104 S/m, roughly a third of "
            "the 0.35 S/m DBS-modelling convention and a quarter of the IT'IS value. "
            "Access resistance scales as 1/sigma, so the choice moves compliance "
            "voltage proportionally."
        ),
    ),
    "mccreery1995": _ref(
        key="mccreery1995",
        authors="McCreery DB, Agnew WF, Yuen TG, Bullara LA",
        title=(
            "Relationship between stimulus amplitude, stimulus frequency and neural "
            "damage during electrical stimulation of sciatic nerve of cat"
        ),
        year=1995,
        venue="Medical & Biological Engineering & Computing",
        volume="33(3)",
        pages="426-429",
        doi="10.1007/BF02510526",
        note=(
            "The measured frequency dependence. 50 -> 100 Hz tripled the damage slope "
            "and lowered the threshold to 0.73x; at 20 Hz damage did not correlate "
            "with amplitude at all. Amplitude is normalised to alpha-component "
            "recruitment, not charge, so no charge-density derating follows."
        ),
    ),
    "butterwick2007": _ref(
        key="butterwick2007",
        authors="Butterwick A, Vankov A, Huie P, Freyvert Y, Palanker D",
        title="Tissue damage by pulsed electrical stimulation",
        year=2007,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="54(12)",
        pages="2261-2267",
        doi="10.1109/TBME.2007.908310",
        pmid="18075042",
        note=(
            "Current-density damage thresholds, the electroporation mode the Shannon "
            "criterion does not describe. Threshold falls as t^-0.5 with pulse width, "
            "is size-independent above 300 um, rises as d^-2 below 200 um, and "
            "saturates after about 50 pulses. Chick CAM and retina; applying it to "
            "cortex is an extrapolation across preparation."
        ),
    ),
    "cogan2016": _ref(
        key="cogan2016",
        authors="Cogan SF, Ludwig KA, Welle CG, Takmakov P",
        title="Tissue damage thresholds during therapeutic electrical stimulation",
        year=2016,
        venue="Journal of Neural Engineering",
        volume="13(2)",
        pages="021001",
        doi="10.1088/1741-2560/13/2/021001",
        pmid="26792176",
        note=(
            "Modern re-evaluation of the Shannon criterion, co-authored at FDA/CDRH. "
            "Establishes that microelectrodes follow a charge-per-phase threshold "
            "(~4 nC/ph) rather than the Shannon codependence, and that in vivo "
            "charge-injection capacity is up to 10x below the saline value."
        ),
    ),
    "rose_robblee1990": _ref(
        key="rose_robblee1990",
        authors="Rose TL, Robblee LS",
        title=(
            "Electrical stimulation with Pt electrodes. VIII. Electrochemically "
            "safe charge injection limits with 0.2 ms pulses"
        ),
        year=1990,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="37(11)",
        pages="1118-1120",
        doi="10.1109/10.61038",
        note=(
            "Origin of the 50-150 uC/cm^2 geometric Pt limit at 0.2 ms pulses, set by "
            "avoiding water reduction/oxidation at approximately -0.6 V and 0.8 V "
            "(Ag|AgCl) at pH 7. Publisher metadata gives paper VIII at 37:1118-1120; "
            "Cogan 2008 ref. 71 prints 'VII' at 37:1119-20, which appears to be an "
            "error in that reference list."
        ),
    ),
    "beebe_rose1988": _ref(
        key="beebe_rose1988",
        authors="Beebe X, Rose TL",
        title=(
            "Charge injection limits of activated iridium oxide electrodes with "
            "0.2 ms pulses in bicarbonate buffered saline"
        ),
        year=1988,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="35",
        pages="494-495",
        doi="10.1109/10.2122",
        note="Cogan 2008 ref. 72; AIROF row of Table 2.",
    ),
    "cogan2006_airof": _ref(
        key="cogan2006_airof",
        authors="Cogan SF, Troyk PR, Ehrlich J, Plante TD, Detlefsen DE",
        title=(
            "Potential-biased, asymmetric waveforms for charge-injection with "
            "activated iridium oxide (AIROF) neural stimulation electrodes"
        ),
        year=2006,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="53",
        pages="327-332",
        doi="10.1109/TBME.2005.862572",
        note="Cogan 2008 ref. 73; source of the AIROF bias dependence.",
    ),
    "robblee1986_tirof": _ref(
        key="robblee1986_tirof",
        authors="Robblee LS, Mangaudis MJ, Lasinsky ED, Kimball AG, Brummer SB",
        title="Charge injection properties of thermally-prepared iridium oxide films",
        year=1986,
        venue="Materials Research Society Symposium Proceedings",
        volume="55",
        pages="303-310",
        source_type="conference",
        note="Cogan 2008 ref. 74; thermal iridium oxide row of Table 2.",
    ),
    "cogan2004_sirof": _ref(
        key="cogan2004_sirof",
        authors="Cogan SF, Plante TD, Ehrlich J",
        title=(
            "Sputtered iridium oxide films (SIROFs) for low-impedance neural "
            "stimulation and recording electrodes"
        ),
        year=2004,
        venue="Proceedings of the IEEE Engineering in Medicine and Biology Society",
        volume="4",
        pages="4153-4156",
        doi="10.1109/IEMBS.2004.1404158",
        source_type="conference",
        note="Cogan 2008 ref. 75; SIROF row of Table 2.",
    ),
    "rose1985_capacitor": _ref(
        key="rose1985_capacitor",
        authors="Rose TL, Kelliher EM, Robblee LS",
        title="Assessment of capacitor electrodes for intracortical neural stimulation",
        year=1985,
        venue="Journal of Neuroscience Methods",
        volume="12",
        pages="181-193",
        doi="10.1016/0165-0270(85)90001-9",
        note="Cogan 2008 ref. 76; Ta/Ta2O5 row of Table 2.",
    ),
    "schmidt1982_capacitor": _ref(
        key="schmidt1982_capacitor",
        authors="Schmidt EM, Hambrecht FT, McIntosh JS",
        title="Intracortical capacitor electrodes: preliminary evaluation",
        year=1982,
        venue="Journal of Neuroscience Methods",
        volume="5",
        pages="33-39",
        doi="10.1016/0165-0270(82)90048-6",
        note="Cogan 2008 ref. 77; Ta/Ta2O5 row of Table 2.",
    ),
    "weiland2002_tin": _ref(
        key="weiland2002_tin",
        authors="Weiland JD, Anderson DJ, Humayun MS",
        title=(
            "In vitro electrical properties for iridium oxide versus titanium "
            "nitride stimulating electrodes"
        ),
        year=2002,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="49",
        pages="1574-1579",
        doi="10.1109/TBME.2002.805487",
        note=(
            "Cogan 2008 ref. 78; TiN row of Table 2. Reports 0.9 mC/cm^2 in vitro at "
            "0.5 ms pulse width on 4000 um^2 electrodes."
        ),
    ),
    "cogan2007_pedot": _ref(
        key="cogan2007_pedot",
        authors="Cogan SF, Peramunage D, Smirnov A, Ehrlich J, McCreery DB, Manoonkitiwongsa PS",
        title="Polyethylenedioxythiophene (PEDOT) coatings for neural stimulation and recording electrodes",
        year=2007,
        venue="Materials Research Society Meeting, Boston, Nov 26-30",
        pages="Abstract QQ2.7",
        source_type="abstract",
        note=(
            "Cogan 2008 ref. 79; the sole source for the 15 mC/cm^2 PEDOT entry in "
            "Table 2. A meeting abstract, not a peer-reviewed paper. The highest "
            "charge-injection value in the table therefore rests on the weakest "
            "source in it."
        ),
    ),
    "nyberg2007_pedot": _ref(
        key="nyberg2007_pedot",
        authors="Nyberg T, Shimada A, Torimitsu K",
        title="Ion conducting polymer microelectrodes for interfacing with neural networks",
        year=2007,
        venue="Journal of Neuroscience Methods",
        volume="160(1)",
        pages="16-25",
        doi="10.1016/j.jneumeth.2006.08.008",
        note=(
            "Cogan 2008 ref. 111. Reports 3.6 mC/cm^2 for PEDOT-PSS on ITO "
            "(GSA 2500 um^2) with 1 ms, 0.5 V pulses -- roughly a quarter of the "
            "Table 2 value, from a peer-reviewed source."
        ),
    ),
    "riedy_walter1996": _ref(
        key="riedy_walter1996",
        authors="Riedy LW, Walter JS",
        title=(
            "Effects of low charge injection densities on corrosion responses "
            "of pulsed 316LVM stainless steel electrodes"
        ),
        year=1996,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="43(6)",
        pages="660-663",
        doi="10.1109/10.495287",
        pmid="8987272",
        note="316LVM: 40 uC/cm^2 reported safe; only 20 uC/cm^2 non-faradaic.",
    ),
    "user_measurement": _ref(
        key="user_measurement",
        authors="(user)",
        title="Locally measured value, not from published literature",
        year=0,
        note=(
            "Placeholder provenance for values supplied by the user's own electrode "
            "characterisation. Never attribute these to a published source."
        ),
    ),
    "rand_woods1971": _ref(
        key="rand_woods1971",
        authors="Rand DAJ, Woods R",
        title="The nature of adsorbed oxygen on rhodium, palladium and gold electrodes",
        year=1971,
        venue="Journal of Electroanalytical Chemistry",
        volume="31(1)",
        pages="29-38",
        doi="10.1016/0368-1874(71)80004-7",
        note=(
            "Platinum pseudocapacitance 210 uC/cm^2 real area (294 uC/cm^2 geometric "
            "at roughness 1.4); value read here via Merrill 2005 footnote 2."
        ),
    ),
    "newman1966": _ref(
        key="newman1966",
        authors="Newman J",
        title="Resistance for flow of current to a disk",
        year=1966,
        venue="Journal of the Electrochemical Society",
        volume="113(5)",
        pages="501-502",
        doi="10.1149/1.2424003",
        note=(
            "Primary-current-distribution access resistance of a disc electrode, "
            "R = 1/(4*kappa*a)."
        ),
    ),
    "brummer_turner1977": _ref(
        key="brummer_turner1977",
        authors="Brummer SB, Turner MJ",
        title="Electrochemical considerations for safe electrical stimulation of the nervous system with platinum electrodes",
        year=1977,
        venue="IEEE Transactions on Biomedical Engineering",
        volume="BME-24(1)",
        pages="59-63",
        doi="10.1109/TBME.1977.326218",
        note=(
            "Pt reversible charge storage capacity 300-350 uC/cm^2 on real area; "
            "value read here via Merrill 2005 Table 2."
        ),
    ),
    "itis2025": _ref(
        key="itis2025",
        authors=(
            "Hasgall PA, Di Gennaro F, Baumgartner C, Neufeld E, Lloyd B, "
            "Gosselin MC, Payne D, Klingenbock A, Kuster N"
        ),
        title=(
            "IT'IS Database for thermal and electromagnetic parameters of "
            "biological tissues, Version 4.2"
        ),
        year=2025,
        venue="IT'IS Foundation",
        doi="10.13099/VIP21000-04-2",
        source_type="database",
        note=(
            "Values read from materialparameterdatabasecurrent20250821.xls, the "
            "release current at 2026-08. Each entry carries an average, standard "
            "deviation, sample size and range aggregated over the primary "
            "literature, which is why it is preferred here over single-paper values."
        ),
    ),
    "pennes1948": _ref(
        key="pennes1948",
        authors="Pennes HH",
        title=(
            "Analysis of tissue and arterial blood temperatures in the resting "
            "human forearm"
        ),
        year=1948,
        venue="Journal of Applied Physiology",
        volume="1(2)",
        pages="93-122",
        note=(
            "Original bioheat equation. The 1948 article predates DOI assignment. The "
            "widely cited reprint is J Appl Physiol 85(1):5-34 (1998), "
            "doi:10.1152/jappl.1998.85.1.5 -- that DOI belongs to the reprint, not to "
            "this record, and must not be attached to it."
        ),
    ),
    "elwassif2006": _ref(
        key="elwassif2006",
        authors="Elwassif MM, Kong Q, Vazquez M, Bikson M",
        title="Bio-heat transfer model of deep brain stimulation-induced temperature changes",
        year=2006,
        venue="Journal of Neural Engineering",
        volume="3(4)",
        pages="306-315",
        doi="10.1088/1741-2560/3/4/008",
        pmid="17946574",
        note=(
            "Brain sigma = 0.35 S/m, thermal conductivity 0.527 W/m/K; "
            "clinical DBS temperature rise up to ~0.8 K."
        ),
    ),
    "lapicque1907": _ref(
        key="lapicque1907",
        authors="Lapicque L",
        title=(
            "Recherches quantitatives sur l'excitation electrique des nerfs "
            "traitee comme une polarisation"
        ),
        year=1907,
        venue="Journal de Physiologie et de Pathologie Generale",
        note="Exponential strength-duration form, quoted as eq. (4.2) in Merrill 2005.",
    ),
    "weiss1901": _ref(
        key="weiss1901",
        authors="Weiss G",
        title="Sur la possibilite de rendre comparables entre eux les appareils servant a l'excitation electrique",
        year=1901,
        venue="Archives Italiennes de Biologie",
        note="Linear charge-duration form Q(W) = Irh*(W + tc).",
    ),
    "asanuma1976": _ref(
        key="asanuma1976",
        authors="Asanuma H, Arnold A, Zarzecki P",
        title=(
            "Further study on the excitation of pyramidal tract cells by "
            "intracortical microstimulation"
        ),
        year=1976,
        venue="Experimental Brain Research",
        volume="26(5)",
        pages="443-461",
        doi="10.1007/BF00238820",
        note=(
            "Strength-duration curves separating cortical cell bodies (chronaxie "
            "0.12-0.2 ms) from axons (0.06-0.13 ms), with shock artifact cancelled. "
            "Also the source of the 1 mm collateral reach that limits the spatial "
            "selectivity of ICMS, and of a functional depression threshold at 80 uA."
        ),
    ),
    "stoney1968": _ref(
        key="stoney1968",
        authors="Stoney SD, Thompson WD, Asanuma H",
        title=(
            "Excitation of pyramidal tract cells by intracortical microstimulation: "
            "effective extent of stimulating current"
        ),
        year=1968,
        venue="Journal of Neurophysiology",
        volume="31(5)",
        pages="659-669",
        doi="10.1152/jn.1968.31.5.659",
        pmid="5711137",
        note="Original current-distance relation I = I0 + k*r^2.",
    ),
    "tehovnik2006": _ref(
        key="tehovnik2006",
        authors="Tehovnik EJ, Tolias AS, Sultan F, Slocum WM, Logothetis NK",
        title="Direct and indirect activation of cortical neurons by electrical microstimulation",
        year=2006,
        venue="Journal of Neurophysiology",
        volume="96(1)",
        pages="512-521",
        doi="10.1152/jn.00126.2006",
        note="Current-distance constant k ~ 675 uA/mm^2 quoted for surface electrodes.",
    ),
}


def cite(key: str) -> Reference:
    """Look up a reference, raising a clear error for unknown keys."""
    try:
        return REFERENCES[key]
    except KeyError:
        raise KeyError(
            f"Unknown reference key {key!r}. Known keys: {sorted(REFERENCES)}"
        ) from None


def bibliography(keys: list[str] | None = None) -> str:
    """Render a sorted plain-text bibliography for the given keys (default: all)."""
    chosen = sorted(set(keys) if keys is not None else REFERENCES)
    return "\n".join(f"[{k}] {cite(k).citation()}" for k in chosen)
