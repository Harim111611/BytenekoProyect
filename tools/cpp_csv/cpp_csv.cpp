#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <sstream>
#include <cctype>
#include <limits>

namespace py = pybind11;

namespace {

// Parsea una línea CSV en un vector<string>, soportando:
// - delimitador configurable
// - comillas dobles
// - comillas escapadas: ""
std::vector<std::string> parse_csv_line(const std::string &line, char delimiter) {
    std::vector<std::string> row;
    row.reserve(32);  // heurística para reducir realocaciones

    std::string cell;
    cell.reserve(line.size());

    bool in_quotes = false;

    for (std::size_t i = 0; i < line.size(); ++i) {
        char c = line[i];

        if (c == '"') {
            // Comilla escapada dentro de un campo: ""
            if (in_quotes && i + 1 < line.size() && line[i + 1] == '"') {
                cell.push_back('"');
                ++i;  // saltar la segunda comilla
            } else {
                // Cambiamos el estado de comillas
                in_quotes = !in_quotes;
            }
        } else if (c == delimiter && !in_quotes) {
            // Fin de celda
            row.emplace_back(std::move(cell));
            cell.clear();
        } else {
            cell.push_back(c);
        }
    }

    // Última celda de la fila
    row.emplace_back(std::move(cell));
    return row;
}

// Implementación base: solo C++, sin tipos de pybind11.
// Se usa tanto en read_csv como en read_csv_dicts.
std::vector<std::vector<std::string>>
read_csv_impl(const std::string &filename, char delimiter) {
    std::ifstream file(filename);
    if (!file.is_open()) {
        throw std::runtime_error("No se pudo abrir el archivo CSV: " + filename);
    }

    std::vector<std::vector<std::string>> result;
    std::string line;

    while (std::getline(file, line)) {
        // Manejo de \r\n (Windows): quitar \r del final si existe.
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }

        // Si quieres saltar filas totalmente vacías
        if (line.empty()) {
            continue;
        }

        auto row = parse_csv_line(line, delimiter);
        result.emplace_back(std::move(row));
    }

    return result;
}

}  // namespace

// Estructuras para validación
namespace validation {

enum class FieldType {
    TEXT,
    NUMBER,
    SCALE,
    SINGLE
};

struct ValidationRule {
    FieldType type;
    double min_value = 0.0;
    double max_value = 10.0;
    std::unordered_set<std::string> valid_options;
};

struct ValidationError {
    size_t row_index;
    std::string column;
    std::string value;
    std::string message;
};

// Trim whitespace
inline std::string trim(const std::string& str) {
    auto start = str.begin();
    while (start != str.end() && std::isspace(*start)) {
        ++start;
    }
    auto end = str.end();
    do {
        --end;
    } while (std::distance(start, end) > 0 && std::isspace(*end));
    return std::string(start, end + 1);
}

// Convierte string a FieldType
FieldType parse_field_type(const std::string& type_str) {
    std::string lower = type_str;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    
    if (lower == "number") return FieldType::NUMBER;
    if (lower == "scale") return FieldType::SCALE;
    if (lower == "single") return FieldType::SINGLE;
    return FieldType::TEXT;
}

// Parsea el esquema de validación desde Python dict
std::unordered_map<std::string, ValidationRule> parse_schema(const py::dict& schema) {
    std::unordered_map<std::string, ValidationRule> rules;
    
    for (auto item : schema) {
        std::string column_name = py::str(item.first);
        py::dict column_rules = py::cast<py::dict>(item.second);
        
        ValidationRule rule;
        
        // Tipo de campo
        if (column_rules.contains("type")) {
            std::string type_str = py::str(column_rules["type"]);
            rule.type = parse_field_type(type_str);
        } else {
            rule.type = FieldType::TEXT;
        }
        
        // Min/max para scale
        if (column_rules.contains("min")) {
            rule.min_value = py::cast<double>(column_rules["min"]);
        }
        if (column_rules.contains("max")) {
            rule.max_value = py::cast<double>(column_rules["max"]);
        }
        
        // Opciones válidas para single
        if (column_rules.contains("options")) {
            py::list options = py::cast<py::list>(column_rules["options"]);
            for (auto opt : options) {
                std::string opt_str = py::str(opt);
                rule.valid_options.insert(trim(opt_str));
            }
        }
        
        rules[column_name] = rule;
    }
    
    return rules;
}

// Valida y convierte un valor según la regla
py::object validate_value(const std::string& value, const ValidationRule& rule, 
                          size_t row_idx, const std::string& column,
                          std::vector<ValidationError>& errors) {
    std::string trimmed = trim(value);
    
    // Valor vacío
    if (trimmed.empty()) {
        return py::none();
    }
    
    switch (rule.type) {
        case FieldType::NUMBER: {
            try {
                size_t pos;
                double num = std::stod(trimmed, &pos);
                // Verificar que se consumió todo el string
                if (pos != trimmed.length()) {
                    errors.push_back({row_idx, column, value, "No es un número válido"});
                    return py::none();
                }
                return py::cast(num);
            } catch (...) {
                errors.push_back({row_idx, column, value, "No es un número válido"});
                return py::none();
            }
        }
        
        case FieldType::SCALE: {
            try {
                size_t pos;
                double num = std::stod(trimmed, &pos);
                if (pos != trimmed.length()) {
                    errors.push_back({row_idx, column, value, "No es un número válido para escala"});
                    return py::none();
                }
                if (num < rule.min_value || num > rule.max_value) {
                    std::ostringstream oss;
                    oss << "Valor fuera de rango [" << rule.min_value << ", " << rule.max_value << "]";
                    errors.push_back({row_idx, column, value, oss.str()});
                    return py::none();
                }
                return py::cast(num);
            } catch (...) {
                errors.push_back({row_idx, column, value, "No es un número válido para escala"});
                return py::none();
            }
        }
        
        case FieldType::SINGLE: {
            if (!rule.valid_options.empty()) {
                if (rule.valid_options.find(trimmed) == rule.valid_options.end()) {
                    errors.push_back({row_idx, column, value, "Opción no válida"});
                    return py::none();
                }
            }
            return py::str(trimmed);
        }
        
        case FieldType::TEXT:
        default:
            return py::str(trimmed);
    }
}

}  // namespace validation

// Función original: devuelve list[list[str]] (vector<vector<string>>)
std::vector<std::vector<std::string>>
read_csv(const std::string &filename, char delimiter = ',') {
    // Liberamos el GIL mientras hacemos I/O y parsing en C++
    py::gil_scoped_release release;
    auto result = read_csv_impl(filename, delimiter);
    return result;
}

// Nueva función: devuelve list[dict], mapeando header -> valor
py::list read_csv_dicts(const std::string &filename, char delimiter = ',') {
    std::vector<std::vector<std::string>> rows;

    {
        // Leer y parsear CSV sin GIL (solo C++)
        py::gil_scoped_release release;
        rows = read_csv_impl(filename, delimiter);
    }  // Aquí se recupera el GIL automáticamente

    py::list py_rows;

    if (rows.empty()) {
        return py_rows;
    }

    const auto &header = rows.front();

    for (std::size_t i = 1; i < rows.size(); ++i) {
        const auto &row = rows[i];
        py::dict d;

        // Emparejar columnas que existan en ambas
        std::size_t cols = std::min(header.size(), row.size());
        for (std::size_t j = 0; j < cols; ++j) {
            d[py::str(header[j])] = py::str(row[j]);
        }

        // Si la fila tiene menos columnas que el header, rellenar con vacío
        if (row.size() < header.size()) {
            for (std::size_t j = row.size(); j < header.size(); ++j) {
                d[py::str(header[j])] = py::str("");
            }
        }

        py_rows.append(std::move(d));
    }

    return py_rows;
}

// Nueva función: leer, validar y convertir datos según esquema
py::dict read_and_validate_csv(const std::string& filename, 
                                const py::dict& schema,
                                char delimiter = ',') {
    std::vector<std::vector<std::string>> rows;
    
    {
        // Leer y parsear CSV sin GIL (solo C++)
        py::gil_scoped_release release;
        rows = read_csv_impl(filename, delimiter);
    }
    
    // Parsear esquema de validación
    auto rules = validation::parse_schema(schema);
    
    py::list validated_data;
    std::vector<validation::ValidationError> errors;
    
    if (rows.empty()) {
        py::dict result;
        result["data"] = validated_data;
        result["errors"] = py::list();
        return result;
    }
    
    const auto& header = rows.front();
    
    // Crear mapa de índice de columnas
    std::unordered_map<std::string, size_t> column_indices;
    for (size_t j = 0; j < header.size(); ++j) {
        column_indices[header[j]] = j;
    }
    
    // Validar y convertir cada fila
    for (size_t i = 1; i < rows.size(); ++i) {
        const auto& row = rows[i];
        py::dict row_dict;
        bool row_has_critical_error = false;
        
        // Procesar cada columna según el header
        size_t cols = std::min(header.size(), row.size());
        for (size_t j = 0; j < cols; ++j) {
            const std::string& col_name = header[j];
            const std::string& cell_value = row[j];
            
            // Si existe regla de validación para esta columna
            auto rule_it = rules.find(col_name);
            if (rule_it != rules.end()) {
                py::object validated = validation::validate_value(
                    cell_value, rule_it->second, i, col_name, errors
                );
                row_dict[py::str(col_name)] = validated;
            } else {
                // Sin regla, pasar como string
                row_dict[py::str(col_name)] = py::str(validation::trim(cell_value));
            }
        }
        
        // Rellenar columnas faltantes con None
        if (row.size() < header.size()) {
            for (size_t j = row.size(); j < header.size(); ++j) {
                row_dict[py::str(header[j])] = py::none();
            }
        }
        
        validated_data.append(std::move(row_dict));
    }
    
    // Convertir errores a lista de dicts Python
    py::list error_list;
    for (const auto& err : errors) {
        py::dict err_dict;
        err_dict["row"] = py::cast(err.row_index);
        err_dict["column"] = py::str(err.column);
        err_dict["value"] = py::str(err.value);
        err_dict["message"] = py::str(err.message);
        error_list.append(std::move(err_dict));
    }
    
    py::dict result;
    result["data"] = validated_data;
    result["errors"] = error_list;
    return result;
}

PYBIND11_MODULE(cpp_csv, m) {
    m.doc() = "CSV reader acelerado en C++ para Byteneko";

    // Mantiene la API original
    m.def(
        "read_csv",
        &read_csv,
        py::arg("filename"),
        py::arg("delimiter") = ',',
        "Lee un archivo CSV y regresa una lista de filas (list[list[str]])."
    );

    // Nueva API: más directa para tu flujo en Django
    m.def(
        "read_csv_dicts",
        &read_csv_dicts,
        py::arg("filename"),
        py::arg("delimiter") = ',',
        "Lee un CSV y regresa una lista de diccionarios usando la primera fila "
        "como encabezado."
    );
    
    // API con validación integrada
    m.def(
        "read_and_validate_csv",
        &read_and_validate_csv,
        py::arg("filename"),
        py::arg("schema"),
        py::arg("delimiter") = ',',
        "Lee un CSV, valida según el esquema y retorna {data: [...], errors: [...]}.\n"
        "Esquema ejemplo: {'Edad': {'type': 'number'}, 'Satisfacción': {'type': 'scale', 'min': 0, 'max': 10}}"
    );
}
