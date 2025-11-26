from typing import Dict, Any, Tuple, Optional, List
import numpy
import re
import warnings
from payload import Payload


# Patrón típico de las columnas sensoriales: "1-3p (6002)"
SENSOR_KEY_REGEX = re.compile(r'^\d+-\d+p \(\d{4}\)$')


class Heatmap:
    """
    - Filtra columnas no sensoriales (p. ej., 'Scan') antes del mapeo (opción 1).
    - Tolera llaves desconocidas sin romper (opción 2) y las reporta vía warnings.
      Si deseas el comportamiento anterior (romper), usa strict=True.
    """

    def __init__(self, payload: Payload, ro: Optional[float] = None, *, strict: bool = False, use_regex_filter: bool = True):
        """
        :param payload: instancia de Payload (usa get_most_recent_data()).
        :param ro: resistencia base opcional para normalizar (derivada).
        :param strict: si True, lanza error si existen llaves desconocidas.
        :param use_regex_filter: si True, aplica filtro por regex de clave sensorial además del filtrado por switcher.
        """
        self.payload_entree = payload.get_most_recent_data()
        self.ro = ro
        self.strict = strict
        self.use_regex_filter = use_regex_filter

    # Calculating the points for the heatmap from the diagonal resistance values for like the 5x41 materials
    # -> CAN HAVE DIFFERENT HORIZONTAL WIDTH BUT SAME OVERALL STRUCTURE OF THE 5x41 and SAME HEIGHT/DEPTH OF 5
    def calc_pts_diagonal(self, switcher: Dict[str, Tuple]) -> numpy.ndarray:
        mapped_pts: Dict[Tuple[int, int], float] = self._mapping_coord(switcher)
        width_list = [k[0] for k in mapped_pts]
        if width_list is None:
            max_width = 0
        else:
            max_width = max(width_list)
        max_height = 4

        # OUTPUT 2D MATRIX WILL HAVE THE DIMENSION: max_width*2 (to account for the half points in the intersections)
        # OUTPUTS WILL BE MAPPED AT TWICE THE COLUMN DIMENSION AND REFLECTED ONCE AT THE PT TO THE LEFT, EXCLUDING
        # THE OUTER MOST PTS
        # THE EXCEPTION CASE, SHIFT RIGHT: (0,0) -> (0,0),(0,1);
        # GENERAL CASE, SHIFT LEFT: (0,2) -> (0,3)(0,4) & (0,3) -> (0,6) (0,5)
        # x max_height
        depth = max_height
        rows = depth + 1
        cols = max_width * 2 + 1
        output_matrix = numpy.full((rows, cols), -1.0, dtype=float)

        real_vals = sorted({r for (r, _) in mapped_pts})

        # THE ITERATION IS BASED ON THE DIAGONAL LINES FROM TOP LEFT (OF NORMAL) TO BOTTOM RIGHT (OF PRIME)
        for norm_num in real_vals:  # 1, 2, ..., max_width
            prim_num = norm_num + (max_height // 2)
            # LOWER BOUND IS PRIME_NUM >= 5 b/c STARTS @ 1 NOT 0
            # BASE CASE INTERCEPTS
            if (norm_num < prim_num) and (prim_num >= max_height + 1) and (norm_num <= max_width - max_height):
                for i in range(max_height + 1):
                    key_a = (norm_num, prim_num)
                    key_b = (norm_num + i, prim_num - 4 + i)

                    if key_a in mapped_pts and key_b in mapped_pts:
                        output_matrix[i][(norm_num + i) + norm_num] = (mapped_pts[key_a] + mapped_pts[key_b]) / 2
                    else:
                        raise RuntimeError(f"HEATMAP CALC. ERROR, KEY DOESN'T EXIST: KEY_A= {key_a}, KEY_B= {key_b}")

            # EDGE CASE NOT THE OUTERMOST
            elif (norm_num < prim_num) and (prim_num <= max_width):

                # RIGHT SIDE: 18-19
                if (max_width - norm_num) < norm_num:
                    itr = max_width - norm_num + 1
                    for i in range(itr):
                        key_a = (norm_num, prim_num)
                        key_b = (norm_num + i, prim_num - 4 + i)

                        output_matrix[i][(norm_num + i) + norm_num] = (mapped_pts[key_a] + mapped_pts[key_b]) / 2

                # LEFT SIDE
                else:
                    itr = norm_num + (max_height // 2)

                    # GO FROM BOTTOM TO TOP INSTEAD
                    for j in range(itr):
                        i = max_height - j
                        key_a = (norm_num, prim_num)
                        key_b = (norm_num + i, prim_num - 4 + i)

                        output_matrix[i][(norm_num + i) + norm_num] = (mapped_pts[key_a] + mapped_pts[key_b]) / 2

        # FOR THE EDGE CASES
        # PTS W/ NO INTERSECTIONS
        # 2-4'
        k = 2
        key_a = (k, k + (max_height // 2))
        output_matrix[0][k * 2] = mapped_pts[key_a]

        # 20-18'
        k = max_width - 1
        key_a = (k, k - (max_height // 2))
        output_matrix[0][k * 2] = mapped_pts[key_a]

        # 2-4'
        k = 2
        key_a = (k, k + (max_height // 2))
        output_matrix[max_height][k * 2] = mapped_pts[key_a]

        # 18-20'
        k = max_width - 1
        key_a = (k - (max_height // 2), k)
        output_matrix[max_height][k * 2] = mapped_pts[key_a]

        # 1-1'
        k = 1
        key_a = (1, 1)
        key_b = (1, 1 + (max_height // 2))
        output_matrix[0][k * 2] = (mapped_pts[key_a] + mapped_pts[key_b]) / 2

        # 3-1'
        k = 1
        key_a = (1, 1)
        key_b = (1, 3)
        output_matrix[max_height][k * 2] = (mapped_pts[key_a] + mapped_pts[key_b]) / 2

        # ONLY IF THE FULL CONFIGURATION OF SENSOR SINCE THIS IS THE ONLY VERTICAL COMPONENTS
        if max_width == 22:
            # 21-19'
            k = max_width
            key_a = (k, k - (max_height // 2))
            key_b = (k, k)
            output_matrix[0][k * 2] = (mapped_pts[key_a] + mapped_pts[key_b]) / 2

            # 19-21'
            k = max_width
            key_a = (k - (max_height // 2), k)
            key_b = (k, k)
            output_matrix[max_height][k * 2] = (mapped_pts[key_a] + mapped_pts[key_b]) / 2

        # FILL IN THE WHITESPACE BETWEEN EACH OF THE PTS W/ THE SURROUNDING AVERAGES
        baseline = output_matrix.copy()
        rows, cols = baseline.shape
        for y in range(rows):
            for x in range(cols):
                if baseline[y, x] == -1:
                    neigh_vals = []

                    # top
                    if y > 0 and baseline[y - 1, x] != -1:
                        neigh_vals.append(baseline[y - 1, x])
                    # bottom
                    if y < rows - 1 and baseline[y + 1, x] != -1:
                        neigh_vals.append(baseline[y + 1, x])
                    # left
                    if x > 0 and baseline[y, x - 1] != -1:
                        neigh_vals.append(baseline[y, x - 1])
                    # right
                    if x < cols - 1 and baseline[y, x + 1] != -1:
                        neigh_vals.append(baseline[y, x + 1])

                    if neigh_vals:
                        output_matrix[y, x] = sum(neigh_vals) / len(neigh_vals)

        return output_matrix

    def _filter_payload_keys(self, switcher: Dict[str, Tuple]) -> List[str]:
        """
        Opción 1 (filtrado previo):
        - Mantén solo llaves que estén en el switcher (whitelist).
        - Si use_regex_filter=True, ignora de entrada las que no parecen sensoriales por regex.
        Retorna la lista de llaves a considerar para el mapeo.
        """
        keys = list(self.payload_entree.keys())

        # Si se activa regex, filtramos a priori por patrón sensorial
        if self.use_regex_filter:
            keys = [k for k in keys if (k in switcher) or SENSOR_KEY_REGEX.match(k)]

        # Al final, conservamos solo las que estén realmente en el switcher (whitelist estricta para el mapeo)
        keys = [k for k in keys if k in switcher]

        return keys

    # RETURNS THE mapping according to the SWITCHER PARAMETER configuration for each col name
    # like 6001 (ohm) = 1 - 1p or (1,1)
    # use coord (tuple) for mapping where (# real number, # prime number) to represent the diagonals -> 2-4p is (2,4)
    # float value is the associated resistance value of the line
    def _mapping_coord(self, switcher: Dict[str, Tuple]) -> Dict[Tuple[int, int], float]:
        """
        Opción 1: filtra antes (whitelist + regex opcional).
        Opción 2: tolera llaves desconocidas (reporta por warning); si strict=True, lanza excepción.
        """
        map_result: Dict[Tuple[int, int], float] = {}
        print(switcher)
        print(self.payload_entree.keys())
        # --- Filtrado previo (Opción 1) ---
        filtered_payload_keys = self._filter_payload_keys(switcher)

        # Para reporte (Opción 2): todo lo que llegó y no está en switcher
        payload_keys_set = set(self.payload_entree.keys())
        switcher_keys_set = set(switcher.keys())
        unknown_keys = sorted(list(payload_keys_set - switcher_keys_set))

        # Si hay desconocidas, decide comportamiento según strict
        if unknown_keys:
            msg = (
                f"[Heatmap] Se ignorarán {len(unknown_keys)} llaves desconocidas (p. ej., columnas auxiliares): "
                f"{unknown_keys[:10]}{' ...' if len(unknown_keys) > 10 else ''}\n"
                f"Sugerencia: verifica tu export o actualiza el switcher si corresponde."
            )
            if self.strict:
                # Comportamiento anterior (romper)
                raise RuntimeError(
                    f"Unknown keys found (strict mode): {unknown_keys}. "
                    f"The payload header must match the switcher."
                )
            else:
                warnings.warn(msg)

        # --- Mapeo tolerante (Opción 2) ---
        for key in filtered_payload_keys:
            convert_key: Optional[Tuple[int, int]] = switcher.get(key)
            if convert_key is None:
                # No debería ocurrir tras el filtrado por whitelist, pero lo ponemos por seguridad.
                warnings.warn(f"[Heatmap] Llave '{key}' filtrada pero no encontrada en switcher. Se omite.")
                continue

            val = self.payload_entree[key]
            if self.ro is None:
                map_result[convert_key] = val
            else:
                map_result[convert_key] = (val - self.ro) / self.ro

        if not map_result:
            raise RuntimeError(
                "No se pudo mapear ninguna clave válida. "
                "Revisa que el switcher corresponda al archivo y que el payload tenga datos."
            )

        return map_result

    # UPDATE THE HEATMAP'S PAYLOAD ENTRE that's being used
    def set_payload_entree(self, payload_entree: Dict[str, Any]):
        self.payload_entree = payload_entree

    # (Opcional) utilitario para validar encabezados sin mapear
    def validate_headers(self, switcher: Dict[str, Tuple]) -> Dict[str, List[str]]:
        """
        Devuelve un dict con: faltantes en payload, desconocidas en payload, y coincidencias.
        Útil para diagnóstico rápido.
        """
        payload_keys = set(self.payload_entree.keys())
        switcher_keys = set(switcher.keys())

        unknown = sorted(list(payload_keys - switcher_keys))
        missing = sorted(list(switcher_keys - payload_keys))
        common = sorted(list(payload_keys & switcher_keys))

        return {
            "unknown_in_payload": unknown,
            "missing_from_payload": missing,
            "matched": common,
        }
