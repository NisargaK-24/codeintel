"""API entrypoint with CLI and framework indicators."""
from orders.processor import OrderProcessor


def app_router_decorator(route_path: str):
    def decorator(fn):
        return fn
    return decorator


@app_router_decorator("/checkout")
def handle_checkout_request(payload: dict) -> dict:
    """Dispatched by framework web router."""
    processor = OrderProcessor()
    return processor.checkout(payload.get("items", []))


def main() -> None:
    """Standard CLI application entry point."""
    print("CodeIntel Sample Application running")


if __name__ == "__main__":
    main()
