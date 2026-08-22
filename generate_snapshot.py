from glp1_watch.pipeline import build_dashboard_snapshot


if __name__ == "__main__":
    snapshot = build_dashboard_snapshot(write_outputs=True)
    print(
        f"{snapshot['as_of_date']} | stance={snapshot['stance']} | "
        f"score={snapshot['overall_score']:.1f}"
    )
