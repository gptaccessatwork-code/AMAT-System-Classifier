import unittest

from system_type_identifier.classifier import SystemTypeClassifier
from system_type_identifier.models import BomItem, BomSnapshot, DecisionStatus
from system_type_identifier.parser import parse_system_number


def item(parent, part, description, depth=1, category="Part"):
    return BomItem(parent, part, description, category, 1.0, depth, (parent, part))


def bom(root, *items, complete=True):
    return BomSnapshot(root, tuple(items), complete, 2)


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.classifier = SystemTypeClassifier()

    def classify(self, system_number, snapshot=None):
        return self.classifier.classify(parse_system_number(system_number), snapshot)

    def test_direct_rules(self):
        cases = {
            "C02130-EY2-GP1": "EPI SINGLE CLUSTER",
            "707844-XA3-GPA": "ETCH SYM3 AP (XA)",
            "708973-XA3T-GPA": "ETCH SYM3 AP (XA)",
            "709839-XA3T-SLD": "ETCH SLD BOX",
            "510170-DF-GPUVB": "DSM PRODUCER SE UV CHAMBER",
        }
        for system_number, expected in cases.items():
            with self.subTest(system_number=system_number):
                self.assertEqual(self.classify(system_number).predicted_system_type, expected)

    def test_xa3_matches_sym3_rule(self):
        decision = self.classify("707844-XA3-GPA")
        self.assertEqual(decision.status, DecisionStatus.CLASSIFIED)
        self.assertEqual(decision.predicted_system_type, "ETCH SYM3 AP (XA)")
        self.assertIn("SYS-XA3-XA3T-GPABC", decision.rule_ids)

    def test_producer_se_one_chamber_gplis(self):
        root = "511098-DF-GPA"
        snapshot = bom(root, item(root, "0190-84840", "LF-F404M-A-EVD-700"))
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.predicted_system_type, "DSM PRODUCER SE 1 CHAMBER WITH GPLIS")

    def test_producer_se_three_chamber_nested_gplis(self):
        root = "502756-DF-GP"
        snapshot = bom(
            root,
            item(root, "502756-DF-GPA", "SYS DF GPA"),
            item(root, "502756-DF-GPB", "SYS DF GPB"),
            item(root, "502756-DF-GPC", "SYS DF GPC"),
            item("502756-DF-GPB", "0190-84840", "L-F404M VALVE", depth=2),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.predicted_system_type, "DSM PRODUCER SE 3 CHAMBER WITH GPLIS")

    def test_coverage_limited_types_require_user_verification(self):
        cases = []
        for index, chambers in enumerate((("GPA", "GPB"), ("GPA", "GPB", "GPC"))):
            for with_gplis in (False, True):
                root = f"5027{index}{int(with_gplis)}-DF-GP"
                rows = [
                    item(root, f"{root[:-2]}{chamber}", f"SYS DF {chamber}")
                    for chamber in chambers
                ]
                if with_gplis:
                    rows.append(item(root, "0244-GPLS", "SYS DF GPLSA"))
                cases.append((root, bom(root, *rows)))

        cases.extend(
            (
                (
                    "710001-XP-GP",
                    bom(
                        "710001-XP-GP",
                        item(
                            "710001-XP-GP",
                            "0250-ONE",
                            "DOC, GAS PANEL CONFIG, 7/7 GPA, ETCH NGGP",
                            category="Document",
                        ),
                    ),
                ),
                (
                    "710002-XP-GP",
                    bom(
                        "710002-XP-GP",
                        item(
                            "710002-XP-GP",
                            "0250-TWO",
                            "DOC GP FULL BUILD, 7/7 PAL AB, ETCH NGGP",
                            category="Document",
                        ),
                    ),
                ),
            )
        )

        for root, snapshot in cases:
            with self.subTest(system_number=root):
                decision = self.classify(root, snapshot)
                self.assertEqual(
                    decision.status,
                    DecisionStatus.VERIFICATION_REQUIRED,
                )
                self.assertIn(
                    "HUMAN-VERIFY-LOW-CONFIDENCE-TYPE",
                    decision.rule_ids,
                )
                self.assertTrue(decision.predicted_system_type)

    def test_full_build_nso_df_gp_can_have_one_chamber_child(self):
        root = "415612R03-DF-GP"
        snapshot = bom(
            root,
            item(root, "415612R03-DF-GPLSB", "NSO DF GPLSB"),
            item(root, "415612R03-DF-GPB", "NSO DF GPB"),
            item(
                "415612R03-DF-GPB",
                "0242-92319",
                "KIT, PECVD, ENCLOSURE SE MK-2",
                depth=2,
            ),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(
            decision.predicted_system_type,
            "DSM PRODUCER SE 1 CHAMBER WITH GPLIS",
        )
        self.assertIn("NSO-FULL-BUILD", decision.rule_ids)

    def test_nso_full_build_reuses_apache_rule(self):
        root = "500678N15-DX-GPB"
        snapshot = bom(root, item(root, "0244-00001", "KIT SYSTEM ENCLOSURE"))
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.predicted_system_type, "DSM APACHE (DX)")
        self.assertIn("NSO-FULL-BUILD", decision.rule_ids)

    def test_gplis_liquid_count_schematic_indicator(self):
        for liquid_count in (1, 2, 3):
            root = f"413470R0{liquid_count}-DG-GPA"
            snapshot = bom(
                root,
                item(root, "0248-09259", "ASSY, ENCLOSURE & COM MAT'L, 6 EXIT, NO"),
                item(
                    root,
                    "0080-TEST",
                    f"SCHEMATIC, 6STK, {liquid_count}-LIQ, W/VAPORIZER, "
                    "STD REG, LAVS, PROD GT",
                    category="Document",
                ),
            )
            with self.subTest(liquid_count=liquid_count):
                self.assertEqual(
                    self.classify(root, snapshot).predicted_system_type,
                    "DSM PRODUCER GT WITH GPLIS",
                )

    def test_liquid_count_requires_schematic_context(self):
        root = "510743-DG-GPA"
        snapshot = bom(root, item(root, "0240-TEST", "KIT, 1-LIQ SUPPLY LINE"))
        self.assertEqual(
            self.classify(root, snapshot).predicted_system_type,
            "DSM PRODUCER GT",
        )

    def test_gplis_token_does_not_match_plastic_tubing_code(self):
        root = "510866-DX-GPA"
        snapshot = bom(root, item(root, "3860-01534", "TBGPLSTC 1/8OD .03WALL PFA"))
        self.assertEqual(
            self.classify(root, snapshot).predicted_system_type,
            "DSM APACHE (DX)",
        )

    def test_gplis_token_accepts_chamber_suffix(self):
        root = "511098-DF-GPA"
        snapshot = bom(root, item(root, "511098-DF-GPLSA", "SYS DF GPLSA"))
        self.assertEqual(
            self.classify(root, snapshot).predicted_system_type,
            "DSM PRODUCER SE 1 CHAMBER WITH GPLIS",
        )

    def test_unrecognized_gt_chamber_needs_review_without_bom(self):
        root = "511374-DG-GPRR"
        parsed = parse_system_number(root)
        self.assertEqual(self.classifier.required_bom_depth(parsed), 0)
        decision = self.classifier.classify(parsed)
        self.assertEqual(decision.status, DecisionStatus.NEEDS_REVIEW)
        self.assertEqual(decision.predicted_system_type, "NEEDS REVIEW")
        self.assertIn("SYS-UNRECOGNIZED-GPLIS-CHAMBER", decision.rule_ids)

    def test_nso_without_enclosure_is_manual_review(self):
        root = "500678N15-DX-GPB"
        decision = self.classify(root, bom(root, item(root, "0244-00001", "KIT VALVE")))
        self.assertEqual(decision.status, DecisionStatus.MANUAL_REVIEW_NSO)
        self.assertEqual(decision.predicted_system_type, "NSO")

    def test_nso_retrofit_document_overrides_enclosure(self):
        root = "509195R04-DG-GPA"
        snapshot = bom(
            root,
            item(root, "0080-RETRO", "DOCUMENT, GAS PANEL RETROFIT", category="Document"),
            item(root, "0720-00225", "CONN ENCLOSURE KIT", depth=2),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.status, DecisionStatus.MANUAL_REVIEW_NSO)
        self.assertEqual(decision.predicted_system_type, "NSO")
        self.assertIn("NSO-RETROFIT-NON-FULL-BUILD", decision.rule_ids)

    def test_nso_retrofit_part_does_not_override_enclosure(self):
        root = "509195R04-DG-GPA"
        snapshot = bom(
            root,
            item(root, "0244-RETRO", "KIT, RETROFIT GAS LINE", category="Part"),
            item(root, "0244-ENC", "SYSTEM ENCLOSURE"),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.status, DecisionStatus.CLASSIFIED)
        self.assertEqual(decision.predicted_system_type, "DSM PRODUCER GT")

    def test_ey3_holder_bom_lds_detection(self):
        root = "C02201-EY3-GP2A"
        holder = "0244-HOLDER"
        snapshot = bom(
            root,
            item(root, holder, "EPI HOLDER"),
            item(holder, "0246-95425", "KIT, LDS 2, BPC TO MAIN", depth=2),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.predicted_system_type, "EPI JOPLIN/HENDRIX WITH LDM")

    def test_es1_maps_to_joplin_without_lds(self):
        root = "C02162-ES1-GPA"
        snapshot = bom(
            root,
            item(
                root,
                "0080-31832",
                "SCHEMATIC, MIX, NO PFD111, AC LDS, RP EPI PRIME GP",
                category="Document",
            ),
            item(root, "0051-46047", "WELDMENT, MAIN DEP-WITHOUT LDS, RFP EPI GP"),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.predicted_system_type, "EPI JOPLIN/HENDRIX")

    def test_ey3_negative_lds_document_does_not_select_ldm(self):
        root = "C02201-EY3-GP2A"
        holder = "0241-82956"
        snapshot = bom(
            root,
            item(root, holder, "EPI HOLDER"),
            item(
                holder,
                "0080-23822",
                "SCHEMATIC, GAS PANEL W/OUT MIX/AC/LDS",
                depth=2,
                category="Document",
            ),
        )
        self.assertEqual(
            self.classify(root, snapshot).predicted_system_type,
            "EPI JOPLIN/HENDRIX",
        )

    def test_pj_ald_tan_and_siconi(self):
        ald_root = "601158-PJ-ZGP1"
        ald = bom(ald_root, item(ald_root, "0244-1", "KIT ALD TaN II", depth=1))
        self.assertEqual(self.classify(ald_root, ald).predicted_system_type, "ALD 2 TAN")

        siconi_root = "B11346-PJ-ZGPC"
        siconi = bom(siconi_root, item(siconi_root, "0244-2", "KIT PROCESS GAS"))
        self.assertEqual(self.classify(siconi_root, siconi).predicted_system_type, "SICONI")

    def test_inoz_positions_samsung_and_explicit_ozonator(self):
        root = "511837-DG-INOZ"
        samsung = bom(
            root,
            item(root, "0241-1", "KIT, POSITION ONE, OZONE RACK"),
            item(root, "0241-2", "KIT, POSITION TWO, OZONE RACK"),
            item(root, "0241-3", "KIT, POSITION THREE, SAMSUNG OZONE RACK"),
        )
        self.assertEqual(
            self.classify(root, samsung).predicted_system_type,
            "CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG",
        )

        explicit = bom(
            root,
            item(root, "0011-16255", "ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE"),
        )
        self.assertEqual(
            self.classify(root, explicit).predicted_system_type,
            "ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE",
        )

    def test_inzc_position_two_only_is_one_chamber(self):
        root = "510971-DG-INZC"
        snapshot = bom(root, item(root, "0241-40896", "KIT, POSITION TWO, OZONE RACK"))
        self.assertEqual(
            self.classify(root, snapshot).predicted_system_type,
            "CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD",
        )

    def test_nso_inzc_positive_position_evidence_passes_full_build_gate(self):
        root = "505556R01-DG-INZC"
        snapshot = bom(
            root,
            item("0241-HOLDER", "0241-40896", "KIT, POSITION TWO, OZONE RACK", depth=2),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(
            decision.predicted_system_type,
            "CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD",
        )
        self.assertIn("NSO-FULL-BUILD-INOZ-EVIDENCE", decision.rule_ids)

    def test_dg_inzc_requires_two_level_bom(self):
        parsed = parse_system_number("509080-DG-INZC")
        self.assertEqual(self.classifier.required_bom_depth(parsed), 2)

    def test_nextgen_consolidated_four_chamber_kit(self):
        root = "710332-KA-GP"
        snapshot = bom(
            root,
            item(root, "0244-03162", "KIT GP CORE 7/7 PALLET 4-CH SLD CENT AP ETCH NG"),
        )
        self.assertEqual(
            self.classify(root, snapshot).predicted_system_type,
            "ETCH NEXTGEN 4 CHAMBER",
        )

    def test_nextgen_doc_dash_abcd_and_space_separated_pallet_chambers(self):
        root = "710332-KA-GP"
        snapshot = bom(
            root,
            item(root, "0250-97225", "DOC, GAS PANEL CONFIG, 6/6-ABCD, SLD, CE", category="Document"),
            item(root, "0244-03190", "KIT 6/6 PALLET NO FRC CH A CENTURA AP ETCH NG"),
            item(root, "0244-03192", "KIT 6/6 PALLET NO FRC CH B CENTURA AP ETCH NG"),
            item(root, "0244-03191", "KIT 6/6 PALLET NO FRC CH C CENTURA AP ETCH NG"),
            item(root, "0244-03218", "KIT 6/6 PALLET NO FRC CH D CENTURA AP ET"),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.predicted_system_type, "ETCH NEXTGEN 4 CHAMBER")
        self.assertEqual(decision.status, DecisionStatus.CLASSIFIED)

    def test_nextgen_explicit_abc_ignores_single_incidental_pallet_chamber(self):
        root = "709387-XP-GP"
        snapshot = bom(
            root,
            item(root, "0244-03336", "KIT GP CORE 6/1/1/6 PAL ABC FRCII-S MLD PROE ETCH NG"),
            item(root, "0250-86970", "DOCUMENT, GAS PANEL CONFIG, 6/1/1/6 CH ABC, PRO-E, ETCH NGGP", category="Document"),
            item(root, "0244-OTHER", "KIT 6/6 PALLET SUPPORT CH B ETCH NGGP"),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.predicted_system_type, "ETCH NEXTGEN 3 CHAMBER")
        self.assertEqual(decision.status, DecisionStatus.CLASSIFIED)

    def test_nextgen_grouped_pallet_chamber_designators(self):
        root = "426137R01-XP-GP"
        snapshot = bom(
            root,
            item(
                root,
                "0248-36021",
                "CIP: KIT GP CORE 6/1/1/6 PALLET CH-A/B/C W/ FRCII-S, "
                "600T, PRO-E ETCH NGGP",
            ),
            item(root, "0242-84705", "KIT, SYSTEM ENCLOSURE, ETCH NGGP", depth=2),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.predicted_system_type, "ETCH NEXTGEN 3 CHAMBER")
        self.assertEqual(decision.status, DecisionStatus.CLASSIFIED)

    def test_nextgen_comma_separated_ab_and_cd_pallets(self):
        root = "708572-XA2-GP"
        snapshot = bom(
            root,
            item(
                root,
                "0244-03268",
                "SLD KIT, GP FULL BUILD, 7/7 PAL AB, 0/4 PAL CD, HTD STK1, "
                "SLD, CENT AP NGGP",
            ),
            item(
                root,
                "0250-83969",
                "DOC, NSR GP FULL BUILD, 7/7 PAL AB, 0/4 PAL CD, HTD STK1, "
                "SLD, CENT AP NGGP",
                category="Document",
            ),
        )
        decision = self.classify(root, snapshot)
        self.assertEqual(decision.predicted_system_type, "ETCH NEXTGEN 4 CHAMBER")
        self.assertEqual(decision.status, DecisionStatus.CLASSIFIED)


if __name__ == "__main__":
    unittest.main()
