import java.math.BigDecimal;
import org.junit.Test;

public class ApplicationServiceTest {
    @Test(expected = IllegalArgumentException.class)
    public void rejectsZeroAmount() {
        new ApplicationService(new BigDecimal("100.00")).submit(BigDecimal.ZERO);
    }
}
