# Vì sao tôi chọn kiến trúc này — ghi chú cho phỏng vấn

*(Note cá nhân, dùng để chuẩn bị trả lời phỏng vấn Data Engineer — có thể dịch
sang tiếng Anh nếu dùng làm blog public.)*

## Bài toán

Dự án mô phỏng một pipeline thu thập dữ liệu giao thông real-time, xử lý và
phục vụ dự đoán tốc độ theo từng đoạn đường. Ý tưởng lấy cảm hứng từ dự án
[TrafficPredictor](https://github.com/vinhky123/TrafficPredictor), nhưng tôi
thiết kế lại theo hướng tập trung vào kỹ năng Data Engineering thay vì
Machine Learning/serverless thuần AWS như bản gốc.

## Vì sao thêm Kafka thay vì gọi API rồi xử lý trực tiếp?

Nếu chỉ gọi API rồi transform ngay trong cùng một tiến trình, hệ thống sẽ:
- Dễ mất dữ liệu nếu bước Transform lỗi hoặc chạy chậm hơn tốc độ Extract
- Không tách được trách nhiệm: một lỗi ở Transform sẽ chặn luôn Extract

Kafka đóng vai trò buffer/queue giữa hai bước, cho phép:
- Extract và Transform chạy độc lập, retry riêng khi lỗi
- Mô phỏng đúng bản chất streaming của dữ liệu giao thông (liên tục, theo
  thời gian thực), thay vì giả định dữ liệu tĩnh theo batch cố định

Đánh đổi: thêm Kafka nghĩa là thêm một hệ thống phải vận hành và giám sát
(broker, topic, consumer group), tăng độ phức tạp so với gọi API xử lý trực
tiếp — chấp nhận được vì mục tiêu là học và thể hiện kỹ năng streaming.

## Vì sao dùng Spark cho Transform thay vì Python thuần?

Với quy mô dữ liệu nhỏ của một dự án sinh viên, Python thuần (pandas) là đủ
để chạy được. Tôi chọn Spark vì hai lý do:
1. Đây là kỹ năng cốt lõi đang ôn cho phỏng vấn (shuffle, partitioning,
   broadcast join, Spark UI) — dùng ngay trong dự án giúp kiến thức không chỉ
   nằm trên lý thuyết.
2. Thiết kế để sẵn sàng scale: nếu dữ liệu tăng lên (nhiều đoạn đường, tần
   suất cao hơn), pipeline không cần viết lại từ đầu.

Đánh đổi: Spark có overhead khởi động (JVM, cluster setup) lớn hơn nhiều so
với việc xử lý bằng pandas cho tập dữ liệu nhỏ — với dữ liệu thật sự nhỏ, đây
là "over-engineering" có chủ đích để phục vụ mục tiêu học tập.

## Vì sao tách hai kho lưu trữ: DynamoDB/MongoDB và PostgreSQL?

Đây là mô phỏng lại pattern OLTP vs OLAP thường gặp trong thực tế:
- **DynamoDB/MongoDB**: tối ưu cho đọc nhanh, phục vụ dashboard/API hỏi
  "tốc độ hiện tại của đoạn đường X" — truy vấn theo key, latency thấp.
- **PostgreSQL + dbt**: tối ưu cho truy vấn phân tích phức tạp (aggregate
  theo thời gian, theo khu vực) và làm nguồn dữ liệu huấn luyện model.

Dùng một kho duy nhất cho cả hai mục đích sẽ buộc phải đánh đổi giữa tốc độ
đọc real-time và khả năng truy vấn phân tích linh hoạt.

## Vì sao Airflow thay vì Step Functions (như bản gốc)?

Bản gốc TrafficPredictor dùng AWS Step Functions vì họ đã cam kết toàn bộ hạ
tầng trên AWS. Tôi chọn Airflow vì:
- Không bị khóa vào một cloud provider cụ thể — kỹ năng dùng được ở bất kỳ
  công ty nào, không riêng AWS
- Airflow phổ biến hơn trong JD tuyển Data Engineer tại Việt Nam mà tôi đang
  nhắm tới (FPT Software, MoMo, VNPay)

## Vì sao thay model transformer (TimeXer) bằng Linear Regression/XGBoost?

Bản gốc dùng TimeXer — một transformer chuyên cho time-series, khá phức tạp
và thiên về Machine Learning Engineer hơn là Data Engineer. Tôi chọn model
đơn giản hơn để:
- Dồn thời gian cho phần data engineering (đúng trọng tâm ứng tuyển)
- Vẫn chứng minh được pipeline train/serve model hoạt động đúng, mà không
  tốn nhiều tuần để hiểu và tune một kiến trúc transformer phức tạp

## Bài học rút ra (cập nhật khi làm xong từng phần)

- *(sẽ bổ sung sau khi hoàn thành Kafka producer/consumer)*
- *(sẽ bổ sung sau khi hoàn thành Spark job)*
- *(sẽ bổ sung sau khi hoàn thành Airflow DAG)*

> Ghi chú: phần này nên được cập nhật liên tục trong quá trình làm, không chỉ
> viết một lần ở cuối — để khi phỏng vấn có thể kể lại đúng những khó khăn
> thực tế đã gặp, không chỉ lý thuyết.
