from scripts.ask import build_parser


def test_build_parser_accepts_filter_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args([
        "--filter-product-area",
        "billing-migration",
        "--compare-filters",
    ])

    assert args.filter_product_area == "billing-migration"
    assert args.compare_filters is True
