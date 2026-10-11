package server.model.items;

import java.io.BufferedReader;
import java.io.FileReader;
import java.util.HashMap;
import java.util.Map;

public class ItemWeight {

    private static final Map<Integer, Double> ITEM_WEIGHTS =
            new HashMap<Integer, Double>();

    static {
        loadWeights();
    }

    private static void loadWeights() {
        try {
            BufferedReader reader =
                    new BufferedReader(new FileReader("./Data/item_weights.txt"));

            String line;

            while ((line = reader.readLine()) != null) {
                line = line.trim();

                // Ignore comments and blank lines.
                if (line.length() == 0 || line.startsWith("#")) {
                    continue;
                }

                String[] parts = line.split("=");

                if (parts.length != 2) {
                    continue;
                }

                int itemId = Integer.parseInt(parts[0].trim());
                double weight = Double.parseDouble(parts[1].trim());

                ITEM_WEIGHTS.put(itemId, weight);
            }

            reader.close();

            System.out.println("[ItemWeight] Loaded "
                    + ITEM_WEIGHTS.size() + " item weights.");

        } catch (Exception e) {
            System.out.println("[ItemWeight] Failed to load item weights.");
            e.printStackTrace();
        }
    }

    public static double getWeight(int itemId) {
        Double weight = ITEM_WEIGHTS.get(itemId);

        if (weight == null) {
            return 0.0;
        }

        return weight;
    }
}