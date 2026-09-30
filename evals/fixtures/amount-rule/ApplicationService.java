import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public final class ApplicationService {
    private BigDecimal remaining;
    private final List<BigDecimal> applications = new ArrayList<>();

    public ApplicationService(BigDecimal quota) {
        if (quota == null || quota.signum() < 0 || quota.stripTrailingZeros().scale() > 2) {
            throw new IllegalArgumentException("invalid quota");
        }
        remaining = quota;
    }

    public void submit(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || amount.stripTrailingZeros().scale() > 2
                || amount.compareTo(remaining) > 0) {
            throw new IllegalArgumentException("invalid amount");
        }
        applications.add(amount);
        remaining = remaining.subtract(amount);
    }

    public int applicationCount() {
        return applications.size();
    }

    public BigDecimal remainingQuota() {
        return remaining;
    }
}
