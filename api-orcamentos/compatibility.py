import re


STEP_CATEGORIES = ["cpu", "cooler", "motherboard", "ram", "storage", "gpu", "psu", "case"]


def _by_category(components: list[dict]) -> dict[str, dict]:
    result = {}
    for component in components:
        cat = component["category"]
        if cat == "kit-ram":
            cat = "ram"
        result[cat] = component
    return result


def _spec(component: dict | None, key: str, default=None):
    if not component:
        return default
    return component.get("technical_specs", {}).get(key, default)


def _compat(component: dict | None, key: str, default=None):
    if not component:
        return default
    return component.get("compatibility", {}).get(key, default)


def _positive_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match and int(match.group()) > 0:
            return int(match.group())
    return None


def _ram_modules(ram: dict) -> int:
    modules = _spec(ram, "modules")
    if isinstance(modules, int) and modules > 0:
        return modules
    if isinstance(modules, str):
        match = re.match(r"\s*(\d+)\s*x", modules, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 2 if ram.get("category") == "kit-ram" else 1


def _capacity_gb(component: dict) -> int | None:
    value = _spec(component, "capacity")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) if value > 0 else None
    if isinstance(value, str):
        match = re.search(r"(\d+)\s*GB", value, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def check_components(components: list[dict], quantities: dict[str, int] | None = None) -> dict:
    selected = _by_category(components)
    errors = []
    quantities = quantities or {}

    cpu = selected.get("cpu")
    cooler = selected.get("cooler")
    motherboard = selected.get("motherboard")
    ram = selected.get("ram")
    gpu = selected.get("gpu")
    psu = selected.get("psu")
    case = selected.get("case")

    if cpu and motherboard and _compat(cpu, "socket") != _compat(motherboard, "socket"):
        errors.append("Processador e placa-mãe usam sockets diferentes.")

    if cpu and cooler:
        cpu_socket = _compat(cpu, "socket")
        cooler_sockets = _compat(cooler, "socket_support", [])
        if cpu_socket not in cooler_sockets:
            errors.append("O cooler não suporta o socket do processador selecionado.")
        cpu_tdp = _spec(cpu, "tdp_watts", 0)
        cooler_max_tdp = _compat(cooler, "max_tdp_watts", 9999)
        if cpu_tdp > cooler_max_tdp:
            errors.append("O cooler não suporta o TDP do processador selecionado.")

    if motherboard and ram and _compat(motherboard, "memory_type") != _compat(ram, "memory_type"):
        errors.append("A memória RAM não corresponde ao tipo aceito pela placa-mãe.")

    if motherboard and ram:
        quantity = quantities.get(str(ram.get("id")), 1)
        installed_modules = _ram_modules(ram) * quantity
        memory_slots = _positive_int(_spec(motherboard, "memory_slots"))
        if memory_slots and installed_modules > memory_slots:
            errors.append(
                f"A memória selecionada exige {installed_modules} slots, mas a placa-mãe possui {memory_slots}."
            )

        item_capacity = _capacity_gb(ram)
        max_capacity = _positive_int(_spec(motherboard, "max_memory_gb"))
        if item_capacity and max_capacity and item_capacity * quantity > max_capacity:
            errors.append(
                f"A memória total excede a capacidade máxima de {max_capacity}GB da placa-mãe."
            )

    if gpu and psu and _compat(gpu, "min_psu_watts", 0) > _spec(psu, "wattage", 0):
        errors.append("A fonte não atende à potência mínima recomendada para a GPU.")

    if motherboard and case:
        form_factor = _compat(motherboard, "form_factor")
        supported = _compat(case, "supported_form_factors", [])
        if form_factor not in supported:
            errors.append("O gabinete não suporta o formato da placa-mãe.")

    if gpu and case and _spec(gpu, "length_mm", 0) > _compat(case, "max_gpu_length_mm", 0):
        errors.append("A placa de vídeo é maior que o espaço suportado pelo gabinete.")

    return {
        "compatible": len(errors) == 0,
        "errors": errors,
        "selected_categories": list(selected.keys()),
    }


def next_category(selected_components: dict[str, str]) -> str | None:
    for category in STEP_CATEGORIES:
        if category == "ram":
            if "ram" not in selected_components and "kit-ram" not in selected_components:
                return "ram"
        elif category not in selected_components:
            return category
    return None
