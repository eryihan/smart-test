package fixture;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

public class ReservationService {
    private final JdbcTemplate jdbc;

    public ReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(String orderId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        int changed = jdbc.update("UPDATE inventory SET available = available - ? WHERE id = 1 AND available >= ?",
                quantity, quantity);
        if (changed != 1) {
            throw new IllegalStateException("insufficient stock");
        }
        jdbc.update("INSERT INTO reservation(order_id, quantity) VALUES (?, ?)", orderId, quantity);
    }
}
